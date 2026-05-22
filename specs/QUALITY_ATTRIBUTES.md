# QUALITY_ATTRIBUTES.md — Concrete Scenarios

> ADD requires that quality attributes be **measurable**, not adjectival.
> "Fast" and "reliable" are useless. The scenarios below are written in the
> standard **Source · Stimulus · Environment · Artifact · Response · Measure**
> format and form the test plan for the architecture.

Every architectural decision in `ARCHITECTURE.md` must trace to one or more of these.

---

## QA-1 · Reliability

### Scenario QA-1.1 — Exchange WebSocket disconnect

- **Source:** Exchange WebSocket server
- **Stimulus:** Connection drops (network blip, exchange maintenance)
- **Environment:** Bot is running in live mode with open positions
- **Artifact:** Market Data Ingestion module
- **Response:** Reconnect with exponential backoff; on reconnect, fetch REST snapshot to fill the gap; resume publishing; do **not** place trades on stale data
- **Measure:** Reconnection within 5 s; gap-recovery snapshot within 10 s; **zero** trades on stale data

### Scenario QA-1.2 — Strategy module crash

- **Source:** Unhandled exception in strategy code
- **Stimulus:** Malformed market snapshot triggers a bug
- **Environment:** Live mode, open orders
- **Artifact:** Orchestration layer
- **Response:** Crash is logged with full stack and snapshot; **kill-switch activates**; pending orders cancelled; bot exits with non-zero code so systemd alerts
- **Measure:** Kill-switch fires within 2 s of unhandled exception; 100% of pending orders cancelled before exit

### Scenario QA-1.3 — Partial fill on one leg

- **Source:** Exchange order book moves between leg-1 and leg-2 placement
- **Stimulus:** Leg 1 fills 100%, leg 2 fills 40%
- **Environment:** Live spatial arbitrage
- **Artifact:** Execution Engine
- **Response:** Detect imbalance; either complete leg 2 at degraded price within configured slippage budget OR hedge the open exposure with a market order back to neutral; record the decision
- **Measure:** Imbalance resolved within 30 s; net unhedged exposure ≤ configured limit (default $50) at all times

---

## QA-2 · Security

### Scenario QA-2.1 — API key leak surface

- **Source:** Developer commits `.env` by accident
- **Stimulus:** Key reaches a public repo
- **Environment:** Production keys configured
- **Artifact:** Repo, secrets configuration
- **Response:** Pre-commit hook blocks `.env`; CI scans for high-entropy strings; keys are IP-whitelisted at the exchange so a leaked key cannot be used from an attacker's IP; trade-only permission means even abuse cannot withdraw funds
- **Measure:** Zero secrets in git history (verified by `gitleaks`); 100% of production keys have withdrawal disabled and IP whitelist set

### Scenario QA-2.2 — Hostile input via exchange feed

- **Source:** Compromised or buggy exchange returns malformed JSON
- **Stimulus:** Field with non-numeric price, negative volume, or null
- **Environment:** Any mode
- **Artifact:** Exchange Adapter, Normalizer
- **Response:** Adapter validates and rejects the message; logs the offense; does **not** propagate to strategy; if rejection rate exceeds threshold for that exchange, the feed is quarantined
- **Measure:** 100% of malformed messages rejected at the boundary; quarantine triggers at >1% rejection over 60 s

### Scenario QA-2.3 — Bypass attempt of risk layer

- **Source:** Future code change (or a misled agent)
- **Stimulus:** Code path attempts to call exchange adapter `place_order` directly
- **Environment:** Any mode
- **Artifact:** Exchange Adapter interface
- **Response:** `place_order` requires a `RiskDecision(approved=True)` argument; type system + runtime check refuses any other call
- **Measure:** Static analysis (custom lint) blocks the pattern; unit test verifies runtime rejection

---

## QA-3 · Performance (Latency & Throughput)

### Scenario QA-3.1 — Detection latency

- **Source:** Exchange WebSocket
- **Stimulus:** A new price tick that creates a profitable spread
- **Environment:** Live mode, 5 exchanges subscribed
- **Artifact:** Market Data → Strategy pipeline
- **Response:** Strategy emits `Opportunity` for the tick
- **Measure:** p50 ≤ 30 ms, p99 ≤ 100 ms from WebSocket-receive to Opportunity-emit

### Scenario QA-3.2 — Order placement latency

- **Source:** Strategy Engine
- **Stimulus:** `Opportunity` produced and approved
- **Environment:** Live mode
- **Artifact:** Risk + Execution + Adapter
- **Response:** First leg's REST order submitted to exchange
- **Measure:** p99 ≤ 250 ms from `Opportunity` emit to HTTP request sent

### Scenario QA-3.3 — Tick throughput

- **Source:** All subscribed exchanges
- **Stimulus:** Sustained tick rate during volatile market
- **Environment:** 5 exchanges × 20 symbols = 100 streams
- **Artifact:** Ingestion + Strategy
- **Response:** No back-pressure, no dropped ticks
- **Measure:** Sustain 5,000 ticks/second for ≥10 minutes with p99 detection latency unchanged

---

## QA-4 · Observability

### Scenario QA-4.1 — Post-mortem reconstruction

- **Source:** Operator after an unexpected loss
- **Stimulus:** "Why did the bot do X at 14:23:07 UTC yesterday?"
- **Environment:** 24 hours later
- **Artifact:** Decision log
- **Response:** Operator can replay the exact `MarketSnapshot`, `Opportunity`, `RiskDecision`, and `Fill` records for that moment, in order, from disk
- **Measure:** Full causal chain reconstructible within 5 minutes for any second of any day in the retention window

### Scenario QA-4.2 — Live health visibility

- **Source:** Operator
- **Stimulus:** "Is the bot healthy right now?"
- **Environment:** Live mode
- **Artifact:** Metrics endpoint or dashboard
- **Response:** Operator sees: per-exchange WebSocket status, tick lag, opportunities/min, orders/min, P&L (paper or real), error rate
- **Measure:** Dashboard refreshes ≤ 5 s; all six metrics present

### Scenario QA-4.3 — Alert on degradation

- **Source:** Bot in normal operation
- **Stimulus:** WebSocket disconnect, or error rate spike, or P&L deviates >2σ from baseline
- **Environment:** Live mode
- **Artifact:** Monitoring
- **Response:** Operator receives an alert (email/Telegram/Slack)
- **Measure:** Alert delivered within 60 s of the triggering condition

---

## QA-5 · Modifiability

### Scenario QA-5.1 — Add a new exchange

- **Source:** Developer
- **Stimulus:** "Add support for Exchange X"
- **Environment:** MVP system in steady state
- **Artifact:** Exchange Adapter Layer
- **Response:** Implement the `ExchangeAdapter` interface for X; register in config; no changes to Strategy, Risk, or Execution modules
- **Measure:** New exchange working in paper mode within **1 working day**; **zero** lines changed in non-adapter modules

### Scenario QA-5.2 — Add a new strategy

- **Source:** Developer
- **Stimulus:** "Add triangular arbitrage to a system that only has spatial"
- **Environment:** MVP in steady state
- **Artifact:** Strategy Engine
- **Response:** New strategy file implements the `Strategy` protocol; registered in config; no other module changed
- **Measure:** New strategy detectable in paper mode within **2 working days**; modified files all live under `src/strategies/`

### Scenario QA-5.3 — Change risk policy

- **Source:** Operator
- **Stimulus:** "Reduce max position size from $1000 to $500"
- **Environment:** Live mode
- **Artifact:** Configuration
- **Response:** Edit config file, restart bot; no code change
- **Measure:** Change takes effect within one restart cycle (<60 s)

---

## QA-6 · Testability

### Scenario QA-6.1 — Strategy unit test

- **Source:** Developer
- **Stimulus:** "Verify strategy emits an Opportunity for this synthetic snapshot"
- **Environment:** CI
- **Artifact:** Strategy Engine
- **Response:** Test constructs a `MarketSnapshot`, calls `strategy.evaluate()`, asserts result; no network, no clock, no DB
- **Measure:** Test runs in <50 ms; full strategy suite runs in <5 s

### Scenario QA-6.2 — Replay of historical data

- **Source:** Developer or operator
- **Stimulus:** "Replay yesterday's ticks against a new strategy"
- **Environment:** Backtest mode
- **Artifact:** Whole pipeline with `PaperExchange` and recorded ticks
- **Response:** Pipeline consumes recorded ticks, produces opportunities and simulated fills, outputs P&L
- **Measure:** Bit-for-bit deterministic replay of recorded ticks; identical run produces identical opportunity stream

### Scenario QA-6.3 — Chaos injection

- **Source:** Developer
- **Stimulus:** Test must verify behavior under WebSocket disconnect, exchange 5xx, partial fill, timeout
- **Environment:** Integration tests
- **Artifact:** Test exchange harness
- **Response:** Harness can inject each failure mode on demand; system reacts per QA-1 scenarios
- **Measure:** All four failure modes covered by integration tests; CI fails if any uncovered path is changed

---

## Priority Matrix (for trade-off conflicts)

When two QAs conflict, use this table.

| QA | Beats… | …Loses to |
|---|---|---|
| QA-2 Security | Everything except a tie with QA-1 | (nothing) |
| QA-1 Reliability | QA-3, QA-4, QA-5, QA-6 | QA-2 |
| QA-3 Performance | QA-5, QA-6 | QA-1, QA-2 |
| QA-4 Observability | QA-5, QA-6 | QA-1, QA-2, QA-3 (slightly) |
| QA-5 Modifiability | QA-6 | All others |
| QA-6 Testability | (nothing) | All others |

> Example: A change that makes the code faster (QA-3) but bypasses the risk
> layer (QA-2) is **always rejected**. A change that improves modifiability
> (QA-5) but adds 50 ms of detection latency (QA-3) is rejected unless the
> latency budget still meets QA-3.1.
