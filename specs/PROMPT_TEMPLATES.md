# PROMPT_TEMPLATES.md — Prompts for Claude Code

> Each template is structured to **trigger Karpathy's four principles** in the
> agent's response. Copy, fill the blanks, paste into Claude Code in VSCode.
>
> Anti-pattern: a vague one-liner like "implement the strategy." Always specify
> the success criterion and the files the agent is allowed to touch.

---

## Template Anatomy

A good prompt for this repo has six parts:

```
1. TASK         — One sentence. What to do.
2. CONTEXT      — Which docs/skills the agent must read first.
3. CONSTRAINTS  — Files allowed to touch; files forbidden.
4. SUCCESS      — One-sentence verifiable criterion.
5. VERIFY       — How to prove it works (test/dry-run/replay).
6. REPORT       — What the agent should tell you when done.
```

Missing any part = the agent will guess. Don't make it guess.

---

## Starter Tasks (use these to bootstrap the repo)

### ST-1 · Scaffold the project

```
TASK
  Scaffold the project structure exactly as described in
  specs/PROJECT_STRUCTURE.md. Create empty __init__.py files, pyproject.toml
  with the dependencies listed in CLAUDE.md § 3, and .env.example with all
  required keys but no real values.

CONTEXT
  Read CLAUDE.md, specs/PROJECT_STRUCTURE.md, specs/ARCHITECTURE.md (§ 4).

CONSTRAINTS
  - Touch only files in src/, tests/, pyproject.toml, .env.example, .gitignore
  - Do NOT implement any module logic. Pass `...` in function bodies.
  - Do NOT install dependencies; only declare them.

SUCCESS
  `python -c "import arbitrage_agent"` succeeds; folder tree matches PROJECT_STRUCTURE.md exactly.

VERIFY
  Run `tree -L 3 src/ tests/` and show the output.

REPORT
  List every file you created. List anything in PROJECT_STRUCTURE.md you
  did NOT create and why.
```

---

### ST-2 · Implement the domain types

```
TASK
  Implement src/arbitrage_agent/domain/ exactly as specified in
  specs/ARCHITECTURE.md § 6 (interfaces).

CONTEXT
  CLAUDE.md, specs/ARCHITECTURE.md § 6, specs/GLOSSARY.md.

CONSTRAINTS
  - Only files under src/arbitrage_agent/domain/ and tests/unit/domain/
  - All dataclasses must be frozen
  - All money values use decimal.Decimal, never float
  - No imports outside stdlib

SUCCESS
  Unit tests verify that: constructing each type works; mutating a frozen
  instance raises; Decimal precision is preserved through serialization.

VERIFY
  `pytest tests/unit/domain/ -v` — all green.

REPORT
  Confirm: which interfaces you implemented; what you intentionally did NOT
  add (e.g., serializers, validators) and why.
```

---

### ST-3 · Implement PaperExchange

```
TASK
  Implement src/arbitrage_agent/exchanges/paper.py — a PaperExchange that
  consumes recorded ticks from disk and simulates fills using real order
  book depth.

CONTEXT
  skills/exchange-integration/SKILL.md, specs/QUALITY_ATTRIBUTES.md § QA-6.2.

CONSTRAINTS
  - Only src/arbitrage_agent/exchanges/paper.py and tests/unit/exchanges/
  - Must implement the ExchangeAdapter protocol (do not change the protocol
    unless you propose the change in REPORT)
  - Deterministic given the same input file

SUCCESS
  Replay of a recorded tick file produces an identical sequence of fills
  on two consecutive runs (QA-6.2).

VERIFY
  pytest test confirming bit-identical fill sequence across two runs.

REPORT
  How slippage is simulated. What assumptions about the order book.
```

---

## Recurring Tasks

### RT-1 · Add a new exchange

```
TASK
  Add support for {EXCHANGE_NAME}.

CONTEXT
  skills/exchange-integration/SKILL.md, specs/QUALITY_ATTRIBUTES.md § QA-5.1.
  Read the official {EXCHANGE_NAME} API docs:
  - WebSocket: {URL}
  - REST: {URL}
  - Rate limits: {URL}

CONSTRAINTS
  - Touch ONLY: src/arbitrage_agent/exchanges/{exchange_name}.py,
    src/arbitrage_agent/exchanges/registry.py (one-line addition),
    tests/integration/exchanges/test_{exchange_name}.py,
    .env.example (add API key placeholders)
  - Do NOT modify strategies/, risk/, execution/, or any other adapter
  - Symbol mapping: convert {EXCHANGE_NAME}'s symbols to our domain Symbol type
    at the adapter boundary. Never let exchange-specific strings leak out.

SUCCESS
  Bot in paper mode subscribes to {SYMBOL_LIST} on {EXCHANGE_NAME} and emits
  MarketSnapshots to the bus.

VERIFY
  Integration test connects in sandbox/testnet mode, receives 100 ticks,
  asserts they parse to valid MarketSnapshots.

REPORT
  Confirm QA-5.1 was honored: list every file touched outside exchanges/.
  Expected count: 0.
```

---

### RT-2 · Add a new strategy

```
TASK
  Add a new {STRATEGY_NAME} strategy.

CONTEXT
  skills/arbitrage-detection/SKILL.md, specs/QUALITY_ATTRIBUTES.md § QA-5.2.

CONSTRAINTS
  - Touch ONLY: src/arbitrage_agent/strategies/{strategy_name}.py,
    src/arbitrage_agent/strategies/__init__.py (one-line registration),
    tests/unit/strategies/test_{strategy_name}.py
  - The strategy must be a pure function of MarketSnapshot (no I/O)
  - All profitability math must subtract fees and slippage estimate

SUCCESS
  Strategy returns Opportunity for hand-crafted favorable snapshot; returns
  None for hand-crafted unfavorable snapshot.

VERIFY
  `pytest tests/unit/strategies/test_{strategy_name}.py -v` — green.

REPORT
  The exact formula used to compute expected_net_profit. The fee assumption
  source (config? hardcoded?). Anything that should be moved to config later.
```

---

### RT-3 · Tighten a risk limit

```
TASK
  Update {LIMIT_NAME} from {OLD} to {NEW}.

CONTEXT
  skills/risk-management/SKILL.md.

CONSTRAINTS
  - This is a CONFIG change, not a code change, unless the limit is hardcoded
    (in which case fix the hardcoding too)
  - Touch ONLY: src/arbitrage_agent/config.py (if needed), .env.example, the test

SUCCESS
  Bot logs the new limit on startup; an order exceeding the new limit is
  rejected with the new threshold in the log line.

VERIFY
  Unit test for risk gate at the new limit.

REPORT
  Where the old value was previously enforced (defense in depth check).
```

---

### RT-4 · Investigate a paper-trade anomaly

```
TASK
  At {TIMESTAMP}, the bot {DESCRIBED_BEHAVIOR}. Investigate and propose
  a minimal fix or a deeper analysis.

CONTEXT
  CLAUDE.md § 1.1 (Think Before Coding). Read the decision log for
  {TIMESTAMP ± 5 minutes}: `logs/decisions.jsonl`.

CONSTRAINTS
  - First message back: NO CODE. Just analysis. State your hypothesis,
    what you would need to confirm it, and what the simplest fix would be.
  - Do not modify code until I approve the analysis.

SUCCESS
  A written analysis I can review before any code changes.

VERIFY
  N/A — this is a read-only investigation step.

REPORT
  Hypothesis. Evidence from logs. Proposed fix vs. proposed deeper test.
```

---

### RT-5 · Add a quality-attribute test

```
TASK
  Implement the test for scenario {QA-X.Y} from specs/QUALITY_ATTRIBUTES.md.

CONTEXT
  specs/QUALITY_ATTRIBUTES.md § {QA-X.Y}, the relevant skill file.

CONSTRAINTS
  - Touch ONLY tests/ + a single test fixture if needed
  - No production code change. If a production change is needed, STOP and
    raise it as a separate task.

SUCCESS
  The test runs and asserts the measure exactly as defined in the scenario.

VERIFY
  Run the test, show output. If it fails, the test is correct and the system
  is at fault — report that, do not "fix" the test.

REPORT
  Pass/fail. If fail, what code change would be needed (do not write it).
```

---

## The Universal Prompt-Hygiene Checklist

Before sending **any** prompt, ask yourself:

- [ ] Did I name **one** success criterion? (not "and also…")
- [ ] Did I list the **files allowed** to touch?
- [ ] Did I list the **files forbidden** to touch?
- [ ] Did I name a **verification step** that does not require my interpretation?
- [ ] Did I ask for a **report** of what was intentionally not changed?

If any answer is no, the prompt invites a Karpathy-principle violation.

---

## Words to Avoid in Prompts

| Avoid | Use Instead |
|---|---|
| "improve" | "change X to Y because Z" |
| "refactor" | "extract this function" — and name it |
| "clean up" | "remove unused import on line N" |
| "make it better" | "reduce p99 latency from 120 ms to under 100 ms" |
| "fix the bug" | "the test in tests/X fails with this output; fix that" |

Vague verbs invite speculative changes. Karpathy Principle 2 fails first
on bad inputs.
