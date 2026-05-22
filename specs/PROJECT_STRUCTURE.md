# PROJECT_STRUCTURE.md — Source Layout

> The folder structure **encodes the architecture**. If a file does not have an
> obvious home, the architecture is wrong or the file is wrong — not the structure.

This document describes the layout Claude Code should produce when implementing.
The structure mirrors the modules in `ARCHITECTURE.md § 4`.

---

## Top-Level Layout

```
crypto-arbitrage-agent/
├── CLAUDE.md                    # Constitution (Karpathy + project rules)
├── README.md                    # Human-readable overview
├── pyproject.toml               # Project metadata + deps (uv or poetry)
├── .env.example                 # Template env file. Real .env is gitignored.
├── .gitignore
├── specs/                       # Architecture & process docs
│   ├── ARCHITECTURE.md
│   ├── QUALITY_ATTRIBUTES.md
│   ├── PROJECT_STRUCTURE.md
│   ├── WORKFLOW.md
│   ├── PROMPT_TEMPLATES.md
│   └── GLOSSARY.md
├── skills/                      # Per-module operating manuals for the agent
│   ├── market-data-ingestion/SKILL.md
│   ├── exchange-integration/SKILL.md
│   ├── arbitrage-detection/SKILL.md
│   ├── risk-management/SKILL.md
│   └── execution-engine/SKILL.md
├── src/
│   └── arbitrage_agent/
│       ├── __init__.py
│       ├── __main__.py          # `python -m arbitrage_agent`
│       ├── config.py            # pydantic-settings; reads .env
│       ├── domain/              # Pure types. No I/O. No deps on other modules.
│       │   ├── __init__.py
│       │   ├── ids.py           # ExchangeId, Symbol, OpportunityId
│       │   ├── money.py         # Price, Volume, Decimal helpers
│       │   └── events.py        # MarketSnapshot, Opportunity, RiskDecision, Fill
│       ├── ingestion/           # Module: Market Data Ingestion
│       │   ├── __init__.py
│       │   ├── bus.py           # In-memory async pub-sub for snapshots
│       │   ├── normalizer.py    # Raw → MarketSnapshot
│       │   └── reconnect.py     # Backoff + gap recovery helpers
│       ├── exchanges/           # Module: Exchange Adapters
│       │   ├── __init__.py
│       │   ├── base.py          # ExchangeAdapter protocol
│       │   ├── paper.py         # PaperExchange — simulated fills
│       │   ├── binance.py       # Concrete adapter (example)
│       │   ├── bybit.py
│       │   └── registry.py      # Build adapters from config
│       ├── strategies/          # Module: Strategy Engine (PURE)
│       │   ├── __init__.py
│       │   ├── base.py          # Strategy protocol
│       │   ├── spatial.py
│       │   ├── triangular.py
│       │   └── funding_rate.py
│       ├── risk/                # Module: Risk Layer
│       │   ├── __init__.py
│       │   ├── gate.py          # The single approve() entry point
│       │   ├── limits.py        # Position, exposure, frequency limits
│       │   └── kill_switch.py
│       ├── execution/           # Module: Execution Engine
│       │   ├── __init__.py
│       │   ├── engine.py        # Order lifecycle state machine
│       │   ├── reconciler.py    # Match expected vs actual fills
│       │   └── hedger.py        # Recover from imbalanced legs
│       ├── persistence/         # Module: Persistence & Observability
│       │   ├── __init__.py
│       │   ├── decision_log.py  # Append-only JSON-line writer
│       │   ├── fills.py         # SQLite-backed fill store
│       │   └── migrations/
│       ├── observability/
│       │   ├── __init__.py
│       │   ├── metrics.py       # Prometheus-style counters/gauges
│       │   ├── logging_setup.py # structlog config
│       │   └── alerts.py
│       └── orchestration/
│           ├── __init__.py
│           ├── pipeline.py      # Wires ingestion → strategy → risk → execution
│           └── lifecycle.py     # Startup, shutdown, kill-switch
├── tests/
│   ├── unit/                    # Pure-function tests, no I/O
│   │   ├── strategies/
│   │   ├── risk/
│   │   └── domain/
│   ├── integration/             # Module-to-module with PaperExchange
│   │   ├── test_pipeline.py
│   │   └── test_reconnect.py
│   ├── fixtures/                # Recorded ticks, synthetic snapshots
│   └── conftest.py
└── scripts/
    ├── record_ticks.py          # Capture live data to disk for replay
    └── replay.py                # Backtest against recorded ticks
```

---

## Rules That the Layout Enforces

| Rule | How the layout enforces it |
|---|---|
| **Domain types have zero dependencies on other modules** | `src/arbitrage_agent/domain/` imports from stdlib only. CI lint blocks other imports. |
| **Strategy Engine is pure** | `src/arbitrage_agent/strategies/` may import `domain/` only. No `exchanges`, no `persistence`. |
| **Risk Layer is the gate** | `src/arbitrage_agent/execution/engine.py` accepts only `RiskDecision(approved=True)`. Adapters' `place_order` requires it too. |
| **Adapters never leak ccxt upward** | `exchanges/` exposes only `domain/` types. `ccxt` import outside `exchanges/` fails lint. |
| **Tests mirror source** | `tests/unit/strategies/test_spatial.py` mirrors `src/.../strategies/spatial.py`. |
| **Documentation lives next to architecture** | All design docs in `specs/`. Per-module how-tos in `skills/`. |

---

## What Goes Where — Quick Decision Tree

> *"I have a new piece of code. Where does it go?"*

```
Is it a data type / dataclass with no behavior?
└─► src/arbitrage_agent/domain/

Does it call an exchange API?
└─► src/arbitrage_agent/exchanges/<exchange_name>.py

Does it decide whether a trade is profitable?
└─► src/arbitrage_agent/strategies/

Does it decide whether a trade is *safe*?
└─► src/arbitrage_agent/risk/

Does it submit, track, or reconcile an order?
└─► src/arbitrage_agent/execution/

Does it write something to disk?
└─► src/arbitrage_agent/persistence/

Does it expose metrics, logs, or alerts?
└─► src/arbitrage_agent/observability/

Does it wire other modules together?
└─► src/arbitrage_agent/orchestration/

Does it not fit any of the above?
└─► STOP. Re-read ARCHITECTURE.md. You probably have a wrong abstraction.
```

---

## Files That Must Exist Before First Run

- `.env` (created from `.env.example`)
- `pyproject.toml`
- Empty SQLite DB (created on first start)
- `logs/` directory (created on first start)

---

## Files That Must **Never** Be Committed

```
.env
*.db
*.sqlite
logs/
.venv/
.idea/
__pycache__/
**/*.pyc
```

The `.gitignore` enforces this. A pre-commit hook (`gitleaks`) is the second line of defense.

---

## Why Not a Monorepo / Microservices Layout?

QA-1 (reliability) and QA-3 (performance) at MVP scale are best served by a
single process. The folder layout above is already prepared for the eventual
split: each `src/arbitrage_agent/<module>/` directory has a clean interface
and could become its own service if the trade-off in `ARCHITECTURE.md § 8`
shifts. Until then, **simpler wins** (Karpathy Principle 2).
