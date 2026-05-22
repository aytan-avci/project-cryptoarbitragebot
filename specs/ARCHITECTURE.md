# ARCHITECTURE.md — Crypto Arbitrage Agent

> Designed using **Attribute-Driven Design (ADD)**: every architectural decision
> is traceable to a quality attribute scenario in `QUALITY_ATTRIBUTES.md`.

---

## 1. Architectural Drivers

Inputs to the ADD process. These are **not optional** — they shape every decision.

### 1.1 Functional Requirements (FR)

| ID | Requirement |
|---|---|
| FR-1 | Ingest real-time price and order book data from N exchanges concurrently |
| FR-2 | Detect arbitrage opportunities (spatial / triangular / funding-rate) |
| FR-3 | Compute net profit *after* fees, slippage estimate, and transfer cost |
| FR-4 | Place, monitor, and reconcile orders across exchanges |
| FR-5 | Enforce risk limits before any order leaves the system |
| FR-6 | Persist a complete audit trail of decisions and fills |
| FR-7 | Operate in paper-trade and live modes with identical decision logic |
| FR-8 | Expose health, metrics, and alerts to an operator |

### 1.2 Quality Attribute Requirements (QA)

Top-ranked attributes for an arbitrage bot, ordered by priority:

| Rank | QA | Why it dominates |
|---|---|---|
| 1 | **Reliability** | A bot that crashes loses opportunities **and** can leave dangling orders |
| 2 | **Security** | A leaked API key drains capital instantly |
| 3 | **Performance (latency)** | Spreads close in milliseconds; slow = unprofitable |
| 4 | **Observability** | If you cannot see what it did, you cannot trust it |
| 5 | **Modifiability** | New exchange, new strategy, new pair — adds are constant |
| 6 | **Testability** | Trading logic must be exercised without real money |

Concrete scenarios for each → `QUALITY_ATTRIBUTES.md`.

### 1.3 Constraints (CN)

Forced from outside; not design choices.

| ID | Constraint | Source |
|---|---|---|
| CN-1 | Python 3.11+, single-process MVP | Team skills, simplicity |
| CN-2 | No withdrawal API permissions, ever | `CLAUDE.md § 2` |
| CN-3 | Must respect exchange rate limits (per venue) | Exchange T&Cs |
| CN-4 | Tax/audit logs retained ≥7 years (jurisdiction-dependent) | Regulation |
| CN-5 | EU DAC8 reporting compliance if operating for EU residents (2026+) | Regulation |

---

## 2. Architectural Design Decisions (ADD Round 1)

### 2.1 Decision: Modular Service Decomposition

**Driver:** QA-1 (Reliability), QA-5 (Modifiability), QA-6 (Testability).

We reject a monolithic application. Functions are split into independently
testable modules with explicit interfaces. If one module fails, the failure is
**isolated** — the data layer crashing must not place trades; the strategy
engine crashing must not corrupt logs.

This is the single most important decision in the system. Every other decision
follows from it.

### 2.2 Decision: Async-First, Single-Process MVP

**Driver:** QA-3 (Performance), CN-1.

Exchange feeds are I/O-bound. `asyncio` gives us concurrent WebSockets without
the complexity of multiprocess coordination. We **do not** introduce
microservices in MVP. Premature distribution = QA-1 cost without QA-3 benefit.

Promotion to multi-process is reserved for the scenario where a single asyncio
loop cannot keep up (measured, not assumed).

### 2.3 Decision: WebSocket-First Ingestion, REST for Recovery

**Driver:** QA-3, QA-1.

Polling REST endpoints is too slow (>100ms typical) and consumes rate-limit
budget. WebSocket subscriptions deliver ticks in <50ms typical. REST is
reserved for: initial snapshot, gap recovery after disconnect, and order
placement.

### 2.4 Decision: Pure-Function Strategy Engine

**Driver:** QA-6 (Testability), QA-1.

The Strategy Engine accepts a market snapshot and returns `Opportunity | None`.
It has no I/O, no side effects, no clock dependency (clock injected). This
makes it deterministic and unit-testable with synthetic order books.

### 2.5 Decision: Risk Layer is a Hard Gate

**Driver:** QA-2 (Security), CN-2.

No order reaches an exchange without passing the Risk Layer's `approve()`
method. There is **no bypass flag, no debug shortcut, no admin override**.
The risk layer is the most reviewed code in the repo.

### 2.6 Decision: Paper and Live Share the Same Decision Path

**Driver:** QA-1, QA-6.

`PaperExchange` and `LiveExchange` implement the same interface. The strategy
engine cannot tell them apart. This means: if it works in paper, the only
difference in live is fill quality — not logic correctness.

### 2.7 Decision: Append-Only Decision Log

**Driver:** QA-4 (Observability), CN-4, FR-6.

Every opportunity detected, every risk check, every order request, every fill
is appended to a structured log (JSON-per-line). The log is the source of truth
for "what did the bot do at 14:23:07?".

---

## 3. Design Concept: Layered + Pipeline Hybrid

```
┌────────────────────────────────────────────────────────────────────┐
│                      OPERATOR / CLI / DASHBOARD                    │
└────────────────────────────────────────────────────────────────────┘
                                  ▲
                                  │  metrics, health, kill-switch
┌────────────────────────────────────────────────────────────────────┐
│  ORCHESTRATION LAYER                                               │
│  ─ Wires modules together; owns the asyncio event loop             │
└────────────────────────────────────────────────────────────────────┘
   │                  │                  │                  │
   ▼                  ▼                  ▼                  ▼
┌──────────┐   ┌──────────┐      ┌──────────┐       ┌──────────┐
│ MARKET   │   │ STRATEGY │      │  RISK    │       │EXECUTION │
│ DATA     │──▶│ ENGINE   │─────▶│  LAYER   │──────▶│ ENGINE   │
│INGESTION │   │ (pure)   │      │ (gate)   │       │          │
└──────────┘   └──────────┘      └──────────┘       └──────────┘
   │                                                       │
   │                                                       │
   ▼                                                       ▼
┌────────────────────────────────────────────────────────────────────┐
│  EXCHANGE ADAPTER LAYER (one per exchange; behind common interface)│
└────────────────────────────────────────────────────────────────────┘
   │                                                       │
   ▼                                                       ▼
┌────────────────────────────────────────────────────────────────────┐
│  PERSISTENCE & OBSERVABILITY                                       │
│  ─ Append-only decision log, fill log, metrics, alerts             │
└────────────────────────────────────────────────────────────────────┘
```

**Why hybrid?** Layered structure gives clear ownership (each layer has a
responsibility). Pipeline structure (data → strategy → risk → execution)
matches the natural flow of an arbitrage event. Each box is one module
with one `SKILL.md`.

---

## 4. Modules (Architectural Elements)

Each module is documented in detail in `skills/<module>/SKILL.md`.

| Module | Responsibility | Owns | Does **not** own |
|---|---|---|---|
| **Market Data Ingestion** | Connect to exchanges, normalize ticks, publish to in-memory bus | WS connections, reconnect logic, time alignment | Strategy, orders |
| **Exchange Adapters** | Translate the unified interface to each exchange's quirks | API keys (read), rate-limit handling, symbol mapping | Strategy decisions |
| **Strategy Engine** | Detect opportunities from market snapshots | Profitability math, spread thresholds | I/O, orders |
| **Risk Layer** | Approve / reject every order | Position limits, exposure caps, kill-switch | Strategy logic |
| **Execution Engine** | Place orders, track fills, reconcile | Order lifecycle state machine | What to trade |
| **Persistence** | Append-only decision and fill log; recoverable state | Disk I/O, schemas | Anything else |
| **Orchestration** | Wire the above; own the event loop | Config, lifecycle, graceful shutdown | Domain logic |

---

## 5. Allocate Responsibilities (the "rules")

These rules prevent the modules from leaking into each other. Violations are
architectural debt, not features.

1. **Market Data Ingestion never decides anything.** It cleans data and publishes.
2. **Strategy Engine is pure.** No `await`, no `time.time()`, no `requests`.
3. **Risk Layer is the only writer of the "approved orders" channel.**
4. **Execution Engine never reads strategy state.** It executes approved orders.
5. **Exchange Adapters never expose ccxt objects upward.** Convert to domain types at the boundary.
6. **Persistence is read-only for everyone except its own writer.** Other modules emit events; the persistence module writes them.
7. **Configuration is read at startup, never mid-flight.** Hot-reload is a v2 concern.

---

## 6. Interfaces (Contracts Between Modules)

Defined precisely in the skill files; sketched here.

### 6.1 `MarketSnapshot` (data → strategy)

```python
@dataclass(frozen=True)
class MarketSnapshot:
    timestamp_utc: datetime
    exchange: ExchangeId
    symbol: Symbol            # e.g., "BTC/USDT"
    bid: Price
    ask: Price
    bid_size: Volume
    ask_size: Volume
```

### 6.2 `Opportunity` (strategy → risk)

```python
@dataclass(frozen=True)
class Opportunity:
    id: OpportunityId
    detected_at: datetime
    strategy: StrategyName            # "spatial" | "triangular" | "funding"
    legs: tuple[OrderIntent, ...]     # 2 for spatial, 3 for triangular
    expected_net_profit: Decimal      # AFTER fees + slippage estimate
    confidence: float                 # 0..1
```

### 6.3 `OrderIntent` (one leg of an opportunity)

```python
@dataclass(frozen=True)
class OrderIntent:
    exchange: ExchangeId
    symbol: Symbol
    side: Literal["buy", "sell"]
    quantity: Volume
    limit_price: Price                # never market orders in MVP
```

### 6.4 `RiskDecision` (risk → execution)

```python
@dataclass(frozen=True)
class RiskDecision:
    opportunity_id: OpportunityId
    approved: bool
    reason: str                       # human-readable; required even on approve
    adjusted_quantity: Volume | None  # may downsize but never upsize
```

---

## 7. Views

### 7.1 Module View
Already shown in § 3 diagram.

### 7.2 Deployment View (MVP)

A single Linux box (cloud or co-located near exchange data centers).
One process. Process manager = `systemd` (or Docker + restart-policy).
Local SQLite for persistence. Logs shipped to a managed log service.

### 7.3 Data-Flow View

```
WebSocket ticks ─► Normalizer ─► Snapshot bus ─► Strategy ─► Opportunity ─►
Risk ─► Approved Order ─► Execution ─► Exchange Adapter ─► REST order ─►
Fill event ─► Reconciler ─► Persistence ─► Metrics
```

---

## 8. Trade-off Analysis

ADD requires we name the trade-offs we accept, not pretend they don't exist.

| Decision | Wins | Costs |
|---|---|---|
| Single-process asyncio | Simpler ops, lower latency between modules | Single point of failure; capped by one CPU core |
| Pure-function strategy | Trivially testable, deterministic | Strategy cannot ask "what's the current balance?" mid-decision; must be precomputed |
| Risk Layer as hard gate | Capital preserved | Slightly more latency per order (~1 ms) |
| SQLite for MVP | Zero ops cost | Won't scale past ~10k trades/day; planned migration to PostgreSQL |
| WebSocket-first | Lowest latency | Reconnect / gap handling is complex code we must own |
| One strategy at MVP | Ships in weeks, not months | Have to wait for v2 to combine strategies |

If a future change makes one of these trade-offs intolerable, that is the
trigger to start ADD Round 2 — **not** to bolt on a workaround.

---

## 9. What This Document Is **Not**

- Not a class diagram. Class names are decided when implementing.
- Not a sprint plan. Implementation order lives in `WORKFLOW.md`.
- Not a UI spec. There is no UI in MVP — only CLI and logs.
- Not a tutorial. It assumes ADD and crypto trading vocabulary
  (see `GLOSSARY.md` if unsure).

---

## 10. When to Update This Document

You update `ARCHITECTURE.md` when:

- A module's responsibilities change.
- A new quality attribute scenario is added that conflicts with a current decision.
- A constraint is added or lifted.
- A trade-off in § 8 becomes unacceptable and triggers redesign.

You do **not** update it for: implementation details, library version bumps,
or new test cases.
