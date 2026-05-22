---
name: risk-management
description: Operating manual for the risk layer — the hard gate every order passes through. Read this BEFORE writing any code under `src/arbitrage_agent/risk/` or modifying anything that touches order approval. Covers position limits, exposure caps, kill-switch logic, and the non-negotiable rule that no order reaches an exchange without RiskDecision(approved=True).
---

# SKILL · Risk Management

## Purpose

Decide, for every `Opportunity` produced by the strategy engine, whether
the bot is permitted to execute it. Output is a `RiskDecision`.

This module is the **last line of defense between code bugs and lost
capital**. It is the most reviewed code in the repo. It is also
deliberately the **simplest** code in the repo — Karpathy Principle 2
applies aggressively here.

---

## The Cardinal Rule

> No order reaches an exchange without a `RiskDecision(approved=True)`.
> **There is no bypass flag. There is no debug shortcut. There is no
> admin override.**

The `ExchangeAdapter.place_order` signature **requires** a `RiskDecision`.
Static analysis fails the build if any code constructs a `RiskDecision`
outside this module. Runtime check refuses any decision whose
`opportunity_id` does not match the order being placed.

If you find yourself wanting to bypass risk "just for testing", use the
`PaperExchange` — never the bypass.

---

## Responsibility Boundary

| In scope | Out of scope |
|---|---|
| Approve / reject every order | Decide what is profitable |
| Position & exposure limits | Place or cancel orders |
| Frequency limits (max orders per minute) | Execute or reconcile fills |
| Kill-switch state and triggers | Persist logs (only emits events) |
| Downsize an opportunity if it would breach limits | Upsize anything, ever |

---

## Quality Attributes This Module Owns

- **QA-2.3** — Bypass attempts must be rejected statically and at runtime.
- **QA-1.2** — When a kill-switch fires, all pending orders are cancelled
  within 2 seconds.
- **QA-5.3** — Limits are config-driven; an operator can tighten them by
  editing config and restarting.

---

## The Decision Function

```python
@dataclass(frozen=True)
class RiskDecision:
    opportunity_id: OpportunityId
    approved: bool
    reason: str                          # required, even on approve
    adjusted_quantity: Volume | None     # may downsize; never upsize

class RiskGate:
    def evaluate(self, opportunity: Opportunity, snapshot: AccountState) -> RiskDecision:
        # Pure-ish: depends on opportunity, current state, and config.
        # No I/O. Reads `AccountState` passed in.
        ...
```

`AccountState` is a snapshot of current positions, balances, recent order
counts. It is **passed in**, not fetched inside risk. (Same purity logic
as strategies — testability requires this.)

---

## Limits in Scope for MVP

These limits are config-driven, all default-tight. The MVP only enables
what is essential.

| Limit | Default | Purpose |
|---|---|---|
| `max_position_value_usd` (per asset) | $500 | Cap exposure per asset |
| `max_gross_exposure_usd` | $1,500 | Cap total open exposure |
| `max_order_value_usd` | $200 | Cap single order |
| `min_order_value_usd` | $20 | Avoid dust trades that lose to fees |
| `max_orders_per_minute` | 30 | Catch runaway loops |
| `max_open_orders` | 5 | Limit unrecovered partials |
| `max_loss_per_day_usd` | $50 | Activate kill-switch if exceeded |
| `min_required_balance_usd` (per venue) | $50 | Refuse if balance is below this |

Each limit's enforcement is in its own function in `limits.py`. Each has its
own unit test. No giant `if/elif` chain.

---

## Decision Order

The gate runs checks in this fixed order. The **first failure stops the
chain** and produces a rejection with the failing reason.

1. Kill-switch is engaged → reject ("kill switch")
2. `EXECUTION_MODE` valid (paper/live, not malformed) → reject if not
3. Opportunity is fresh (within `valid_for_ms`) → reject if stale
4. `expected_net_profit ≥ min_profit_threshold` → reject if not
5. Per-venue connectivity OK → reject if disconnected
6. Per-asset position would stay under limit after fill → if not, try
   downsize; if still infeasible, reject
7. Gross exposure would stay under limit → ditto
8. Order value within `[min_order_value, max_order_value]` → ditto
9. `orders_per_minute` not exceeded → reject if so
10. Min required balance per venue present → reject if not

If **all** checks pass: `RiskDecision(approved=True, reason="all checks passed", ...)`.

---

## Downsize Policy

Some limits permit a smaller version of the same trade. The gate may set
`adjusted_quantity` to a lower value. Rules:

- Never *upsize*.
- After downsizing, **re-run the profitability check**: a smaller trade may
  no longer cover fees, in which case reject.
- Downsize only **once per evaluation**. Don't iterate.

---

## The Kill-Switch

A single boolean flag with these triggers:

- Unhandled exception anywhere in the pipeline (orchestration catches and sets)
- Realized P&L for the day breaches `max_loss_per_day_usd`
- Rejection rate (orders rejected by exchange) exceeds threshold
- Manual operator command (`kill` CLI or signal)

When engaged:

1. New opportunities are rejected at step 1 of the decision chain.
2. Pending orders are **cancelled** (execution module is told).
3. Operator is alerted.
4. Bot **does not** auto-recover. Restart is manual after operator
   investigation. (Phase 3+ rule — see `WORKFLOW.md`.)

The kill-switch's state is in-process. If the process restarts, the switch
resets — **but** the daily P&L counter is loaded from persistence on startup,
so a freshly-restarted bot does not skip the loss-breach check.

---

## What This Module Is **Not**

- Not a strategy refinement layer. If you want to *tune* an opportunity's
  expected profit, that lives in the strategy.
- Not a smart hedger. Recovery from imbalanced legs lives in execution.
- Not an alerting system. It emits events; observability sends alerts.

---

## Anti-Patterns

| Anti-pattern | Why it kills you |
|---|---|
| "Just one bypass flag for testing" | Defeats the whole module. Use `PaperExchange`. |
| Catching the rejection and retrying | Rejections are signals, not transients. Investigate them. |
| Adding a new limit by editing an existing function | Add a new function. Single responsibility per limit. |
| Risk reading account state from the exchange directly | I/O inside risk = untestable. State is passed in. |
| Approving without setting `reason` | The audit log loses traceability. Always set `reason`. |
| Loading limits at evaluation time from disk | Limits read at startup. Restart to change. (QA-5.3) |

---

## Testing This Module

- **Each limit** has unit tests for: at-limit, below-limit, above-limit,
  edge cases (zero, exactly equal).
- **The decision order** is verified by a test that engineers a snapshot
  failing two checks and asserts the **first** is reported (proves order).
- **Kill-switch** has tests for each trigger and for the "engaged → all
  reject" behavior.
- **Bypass attempts** — a static analysis test plus a runtime test that
  constructs a fake approved decision with wrong `opportunity_id` and
  verifies the adapter refuses.

Tests live in `tests/unit/risk/`.

---

## When to Update This Skill

- A new limit type is added (operator policy change)
- The kill-switch gains a new trigger source
- The decision-order rules change (this is a major event; document the
  rationale in the PR)
