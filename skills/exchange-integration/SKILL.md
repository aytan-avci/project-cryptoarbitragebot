---
name: exchange-integration
description: Operating manual for adding and maintaining exchange adapters. Read this BEFORE writing any code under `src/arbitrage_agent/exchanges/` or adding/configuring a new exchange. Covers the ExchangeAdapter protocol, symbol mapping, API key handling, rate limits, and the PaperExchange contract.
---

# SKILL · Exchange Integration

## Purpose

Translate between the unified domain model and each exchange's specific
quirks (symbol formats, fee schedules, order types, rate limits, error codes).

**Exchanges are leaky.** They behave inconsistently, change without notice,
and have undocumented edge cases. This module's job is to **stop the leak**
at the module boundary so the rest of the system can pretend all exchanges
are the same.

---

## Responsibility Boundary

| In scope | Out of scope |
|---|---|
| Implement `ExchangeAdapter` protocol per exchange | Decide what to trade |
| Map domain symbols ↔ exchange-native symbols | Risk checks |
| Translate exchange error codes to domain errors | Strategy logic |
| Apply rate-limit policy per venue | Persistence |
| Hold API credentials (read from config) | Anything in `strategies/`, `risk/`, `execution/`, `ingestion/` |

**Critical rule:** `ccxt` (or any exchange-specific library) **must not be
imported outside `src/arbitrage_agent/exchanges/`.** The rest of the system
sees only the protocol.

---

## The Protocol (`base.py`)

```python
class ExchangeAdapter(Protocol):
    @property
    def id(self) -> ExchangeId: ...

    async def subscribe(self, symbols: list[Symbol], on_snapshot: SnapshotCallback) -> None:
        """Open WS, subscribe to symbols, call on_snapshot for each tick."""

    async def fetch_book_snapshot(self, symbol: Symbol) -> MarketSnapshot:
        """REST fallback for gap recovery."""

    async def place_order(self, intent: OrderIntent, decision: RiskDecision) -> OrderId:
        """RiskDecision(approved=True) is REQUIRED. Any other input -> raise."""

    async def cancel_order(self, order_id: OrderId) -> None: ...

    async def fetch_balance(self, asset: Asset) -> Volume: ...

    async def fetch_fills(self, since: datetime) -> list[Fill]: ...
```

Implementations live in files like `binance.py`, `bybit.py`, `coinbase.py`.
Each is a single class implementing this protocol. Nothing more.

---

## PaperExchange (always present)

The `PaperExchange` is the **first** adapter implemented. It:

- Consumes a recorded tick file (`scripts/record_ticks.py` produces these)
- Or proxies snapshots from a real adapter while simulating fills locally
- Simulates fills using **real order book depth** at the time of the order
  (not a constant spread!). Slippage is computed by walking the book.
- Is deterministic given the same input.

**Why this matters:** the strategy/risk/execution code cannot distinguish
`PaperExchange` from `BinanceAdapter`. This is the foundation of QA-6.2
(deterministic replay) and QA-1 (the same code path is tested in paper).

---

## Symbol Mapping

Every exchange uses different symbol notation:

- Binance: `BTCUSDT`
- Bybit: `BTCUSDT` (perp) vs `BTC/USDT` (spot, sometimes)
- Coinbase: `BTC-USD`
- Kraken: `XBT/USD`
- Our domain: `BTC/USDT` (slash separator; ISO-ish where possible)

Each adapter owns a `_to_native(symbol)` and `_from_native(raw)` pair.
Tested per adapter.

**Never** let a native string escape the adapter. Domain code sees only
`Symbol("BTC/USDT")`.

---

## API Keys (CN-2, QA-2.1)

- Loaded from environment via `pydantic-settings` (config.py).
- **Must** be trade-only on the exchange (withdraw permission disabled).
- **Should** be IP-whitelisted at the exchange.
- The adapter receives them as a parameter at construction; never reaches
  out to read them itself.
- Logged-on-startup line names which exchanges have credentials configured
  but **never** logs the secret itself.

If `EXECUTION_MODE=paper`, real credentials are not required.

---

## Rate Limits (CN-3)

Every exchange has different limits:

- Binance: ~1200 weight/min on REST, 5 messages/sec on WS
- Bybit, Coinbase, others: each different

Each adapter owns a **token-bucket** (or equivalent) for its venue. Calls
to the exchange acquire a token; if exhausted, the call waits.

**Risk:** rate limits are global per API key, not per process. If the same
key is reused elsewhere, your bot's accounting is wrong. **Solution:** one
API key per running bot instance.

---

## Error Translation

Each exchange returns errors in its own format. The adapter normalizes them
to a small set of domain exceptions:

```python
class ExchangeError(Exception): ...
class RateLimited(ExchangeError): ...
class InsufficientFunds(ExchangeError): ...
class OrderNotFound(ExchangeError): ...
class MarketHalted(ExchangeError): ...
class InvalidOrder(ExchangeError): ...
class TemporaryFailure(ExchangeError): ...   # retryable
class PermanentFailure(ExchangeError): ...   # do not retry
```

Anything not classified maps to `TemporaryFailure` and is retried; the
unknown error code is **logged** so it can be classified in a follow-up PR.

---

## Adding a New Exchange (QA-5.1)

The full checklist:

- [ ] Read exchange's official API docs (WS + REST).
- [ ] Create `src/arbitrage_agent/exchanges/<exchange>.py` with one class
      implementing `ExchangeAdapter`.
- [ ] Add `_to_native` / `_from_native` symbol maps; unit-test both directions.
- [ ] Add token-bucket sized to the exchange's documented limit minus 20%
      (margin against rate-limit penalties).
- [ ] Map exchange error codes → domain exceptions.
- [ ] Register the adapter in `exchanges/registry.py` (one line).
- [ ] Add API key placeholders to `.env.example`.
- [ ] Integration test against the exchange's **sandbox/testnet** if it has one.

**Files touched:** only those above. If your diff touches `strategies/`,
`risk/`, or `execution/`, you have violated QA-5.1 and should stop.

---

## Common Mistakes

| Mistake | Fix |
|---|---|
| Using `float` for prices from the exchange JSON | Parse to `Decimal` immediately at the boundary |
| Leaking ccxt `Order` objects out of the module | Return only domain types |
| Catching `ccxt.ExchangeError` and continuing | Translate to a domain exception, then propagate |
| Hardcoding fee values in the strategy | Adapter exposes a `fee_for(side, maker_or_taker)` method, config-driven |
| Sharing one HTTP session across exchanges | One session per adapter; isolates failures |
| Logging API responses including keys/signatures | Strip secrets before logging; or do not log full responses |

---

## When to Update This Skill

- A new exchange has a fundamentally different model (e.g., on-chain DEX)
  that requires extending the protocol
- A common bug repeats across adapters and a guideline must be added
- The `ExchangeAdapter` protocol changes (this is a major event)
