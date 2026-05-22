# WORKFLOW.md — Development & Promotion Path

> How code goes from idea → paper-trade → live, without losing money.
> Every phase has an exit gate. **No skipping gates.**

---

## The Four Phases

```
   PHASE 1            PHASE 2              PHASE 3            PHASE 4
┌─────────────┐   ┌──────────────┐   ┌──────────────┐   ┌──────────────┐
│   DESIGN    │──▶│ PAPER-TRADE  │──▶│ MICRO-LIVE   │──▶│   SCALE      │
│  Scaffold + │   │ With real    │   │ Smallest     │   │  Capital up  │
│  unit tests │   │ market data  │   │ allowed size │   │  if stable   │
└─────────────┘   └──────────────┘   └──────────────┘   └──────────────┘
   Gate: tests       Gate: 30 days     Gate: 7 days        Gate: ongoing
   pass + spec       stable + Sharpe   profitable +        monitoring
   reviewed          > 0 on paper      no incidents
```

Each gate is **objective**, not a feeling.

---

## Phase 1 — Design & Scaffold

### Goal
Produce a runnable skeleton that detects opportunities on **synthetic data**.

### Tasks (in order)
1. Implement `domain/` types.
2. Implement `PaperExchange` (returns canned ticks).
3. Implement one strategy (`spatial.py` recommended, or `funding_rate.py` for lowest risk).
4. Implement `risk/gate.py` with the simplest viable limits.
5. Implement `execution/engine.py` with paper-only fills.
6. Implement `orchestration/pipeline.py` wiring all of the above.
7. Write unit tests for strategy and risk (synthetic snapshots).

### Exit Gate
- [ ] `pytest` green; coverage ≥ 80% on `strategies/` and `risk/`
- [ ] `python -m arbitrage_agent --mode=paper --source=synthetic` runs for 60 s without error
- [ ] At least one opportunity detected against a hand-crafted favorable snapshot
- [ ] `ARCHITECTURE.md` review: no module talks to a module it should not

---

## Phase 2 — Paper-Trade with Real Market Data

### Goal
Run against **live exchange data** but with simulated fills. Measure realism.

### Tasks
1. Implement one real exchange adapter (`binance.py` or `bybit.py`).
2. Connect WebSocket; record ticks to disk for later replay (`scripts/record_ticks.py`).
3. Implement reconnect + gap recovery (QA-1.1).
4. Wire `PaperExchange` to compute simulated fills using **real order book depth**, not a constant spread.
5. Add metrics dashboard: opportunities/min, simulated P&L, latency p50/p99.
6. Add alerts: WebSocket disconnect, error rate spike.

### What "Stable" Means at This Gate

| Metric | Requirement |
|---|---|
| Uptime over rolling 7 days | ≥ 99.5% |
| Unhandled exceptions | 0 |
| Detection latency p99 | ≤ 100 ms (per QA-3.1) |
| Simulated Sharpe ratio | > 0 (note: paper Sharpe is optimistic) |
| Reconnect success rate | 100% |

### Exit Gate
- [ ] **30 calendar days** of continuous paper trading meeting the above metrics
- [ ] Replay test: same recorded ticks twice → identical opportunity stream (QA-6.2)
- [ ] At least one induced failure handled gracefully (kill WebSocket → reconnect)
- [ ] All QA scenarios in `QUALITY_ATTRIBUTES.md` either tested or explicitly deferred

---

## Phase 3 — Micro-Live

### Goal
Validate that the **execution side** works. Profit is not the goal — surviving is.

### Pre-flight Checklist
- [ ] Exchange API keys are **trade-only**, **IP-whitelisted**, **rotated from a known-clean machine**
- [ ] `.env` is gitignored and verified absent from history (`gitleaks`)
- [ ] Position limits set to the **minimum order size the exchange allows**
- [ ] Kill-switch tested in paper mode
- [ ] On-call alert channel (Telegram/Slack/PagerDuty) confirmed working
- [ ] Tax logging verified (every fill in `persistence/fills.py`)
- [ ] You can answer: "If this loses 100% of allocated capital in the next hour, what is the worst-case dollar amount?" — and you are comfortable losing that.

### Operating Rules in Phase 3

1. **Capital allocated = the amount you are willing to lose entirely.** Not a target return, a maximum loss.
2. **Sit with the bot.** First 24 hours: human watches the dashboard.
3. **No code changes** during this phase except to fix bugs that block operation. Feature work waits.
4. **One incident report per anomaly.** Even small ones.

### Exit Gate
- [ ] **7 calendar days** continuous operation
- [ ] Zero unexpected losses (slippage is expected; bugs causing loss are not)
- [ ] At least one full opportunity-to-fill cycle on each connected exchange
- [ ] Reconciler verified: every order has a matched fill or explicit cancellation in the log

---

## Phase 4 — Scale

### Goal
Increase position size **gradually** while monitoring.

### Scaling Rule
Position size doubles only after **2 weeks of stable operation** at the current size.

Stability = the Phase 2 metrics + zero unexpected P&L excursions > 2σ.

If any metric degrades, **scale back down**, do not adjust the metric.

---

## Daily Routine (Phase 3+)

| When | What |
|---|---|
| Morning | Glance at dashboard. Check overnight alerts. |
| Whenever | Respond to alerts. Always investigate before silencing. |
| Weekly | Review fill log: top 10 best, top 10 worst opportunities. What went right/wrong? |
| Monthly | Reconcile against exchange's own statements. Tax export. |

---

## Git Workflow

- Branch per task: `feat/add-bybit-adapter`, `fix/reconnect-race`
- One PR ≈ one success criterion (Karpathy Principle 4)
- PR description **must** state:
  - The success criterion (one sentence)
  - The QA scenario(s) it addresses
  - What was intentionally not changed (Karpathy Principle 3)
- CI must pass before merge. CI runs: lint, type-check, unit, integration

---

## How Claude Code Joins the Workflow

For each task:

1. Operator writes a request (use a `PROMPT_TEMPLATES.md` template if applicable).
2. Claude Code reads `CLAUDE.md` (always in context) and the relevant `SKILL.md`.
3. Claude Code follows the **6-step Decision Loop** (`CLAUDE.md § 4`):
   READ → CLARIFY → PLAN → IMPLEMENT → VERIFY → REPORT.
4. Operator reviews the PR against this workflow's gates.
5. Merge only after gates pass.

---

## Anti-Patterns to Avoid

| Anti-pattern | Why it kills the project |
|---|---|
| "We're 95% done, let's go live" | Phase 2 → Phase 3 gate exists for a reason. Skipping it loses real money. |
| "Just add a flag to bypass the risk layer for testing" | C2 violation. Tests use `PaperExchange`, not bypass flags. |
| "Refactor the whole strategy module while adding this strategy" | Karpathy Principle 3 violation. Surgical changes. |
| "The bot has been running for an hour without issues, scale up" | Stability is measured in weeks at this scale, not hours. |
| "It's just one withdrawal permission, for convenience" | C1 violation. No exceptions. Ever. |
