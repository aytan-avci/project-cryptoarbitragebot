---
name: market-data-ingestion
description: Operating manual for the market data ingestion module. Read this BEFORE writing any code under `src/arbitrage_agent/ingestion/` or modifying exchange data flow. Covers WebSocket subscription, normalization, reconnect/gap recovery, and the in-memory bus contract.
---

# SKILL · Market Data Ingestion

## Purpose

This module connects to exchange data feeds, **normalizes** raw messages into
`MarketSnapshot` events, and **publishes** them on an in-memory bus that the
strategy engine subscribes to.

It is the **only** module that talks to exchange data feeds. If you find
yourself parsing exchange WebSocket frames anywhere else in the codebase,
that is a bug.

---

## Responsibility Boundary

| In scope | Out of scope |
|---|---|
| Open and maintain WebSocket connections | Decide whether to trade |
| Subscribe to symbols listed in config | Place orders |
| Convert raw frames → `MarketSnapshot` | Persist snapshots to disk (recording is a separate script) |
| Reconnect with backoff, recover gaps via REST | Mutate state of other modules |
| Validate messages; drop malformed frames | Compute fees, slippage, P&L |
| Publish to the in-memory bus | Anything in `strategies/`, `risk/`, `execution/` |

---

## Quality Attributes This Module Owns

- **QA-1.1** — Reconnect within 5 s, gap recovery within 10 s, zero trades on stale data.
- **QA-2.2** — Reject malformed messages at the boundary; quarantine misbehaving feeds.
- **QA-3.1** — Contribute < 30 ms to the detection-latency budget.
- **QA-3.3** — Sustain 5,000 ticks/second without back-pressure.

---

## The Contract

The module exposes exactly one outbound type:

```python
@dataclass(frozen=True)
class MarketSnapshot:
    timestamp_utc: datetime    # Exchange-reported time if available, else local UTC at receive
    exchange: ExchangeId
    symbol: Symbol             # Normalized (e.g., "BTC/USDT"), never exchange-native
    bid: Price                 # Decimal
    ask: Price                 # Decimal
    bid_size: Volume           # Top-of-book size
    ask_size: Volume
```

**Snapshots are immutable.** Subscribers must not mutate them.

---

## In-Memory Bus

A minimal pub-sub built on `asyncio.Queue`s. One queue per subscriber.
Publisher does not block on slow subscribers (drops with a counter and log).

Why not a real message queue (Redis, NATS)? **Karpathy Principle 2.** MVP
runs in one process. If we ever split into services, we replace this bus
with the queue of choice. The interface (`bus.subscribe()`, `bus.publish()`)
stays the same.

---

## Reconnect & Gap Recovery (QA-1.1)

Standard pattern:

1. **Connect** with timeout.
2. On disconnect: schedule reconnect with **exponential backoff**
   (start 1 s, cap 60 s, jitter ±20%).
3. On successful reconnect: **fetch a REST snapshot** of the order book
   for each subscribed symbol; publish a synthetic `MarketSnapshot` with a
   `recovery=True` flag (or equivalent metadata in the event).
4. **Resume** WS subscription.
5. **Until step 3 completes, do not publish any WS-derived snapshot.**
   Stale data is worse than no data.

The reconnect logic lives in `reconnect.py` and is the **single owner** of
this state machine. Adapters call into it; they do not implement their own.

---

## Message Validation (QA-2.2)

Every frame from the wire passes a validator that checks:

- Required fields present
- Prices are positive `Decimal`s
- Volumes are non-negative `Decimal`s
- Timestamp is parseable and within reasonable bounds (not from 1970, not future)
- Symbol maps to a configured `Symbol`

Validation failures:

- **Log** with the raw frame (truncated) and the failure reason
- **Drop** the frame (do not propagate)
- **Increment** a per-exchange rejection counter

If rejection rate exceeds **1% over 60 s** for an exchange, mark the feed
**quarantined**. Strategy module is told to ignore that exchange. Operator
is alerted.

---

## Time Handling

- All timestamps are **UTC** internally, `datetime` with `tzinfo=UTC`.
- Use the exchange's reported event time when available; fall back to local
  receive time only if missing.
- **Never use `datetime.now()` without `tz=UTC`.** This is a common bug source.
- Clock skew between exchanges is normal (~10 ms). Strategies must tolerate it.

---

## Performance Notes

- WebSocket parsing is the hot path. Use `orjson` for JSON, **not** stdlib `json`.
- Avoid creating intermediate dicts/strings between wire and `MarketSnapshot`.
- Profile before optimizing. The 30 ms budget is generous; don't burn it on speculation.

---

## Testing This Module

- **Unit tests** for the normalizer: given canned raw frames, expect specific snapshots.
- **Unit tests** for the validator: given malformed frames, expect rejection.
- **Integration test** using a recorded tick file replay; assert the snapshot
  stream is identical across runs.
- **Chaos test** for reconnect: kill the WS, assert reconnect within budget,
  assert no stale snapshots published in the gap.

Tests live in `tests/unit/ingestion/` and `tests/integration/ingestion/`.

---

## Common Mistakes (and how to avoid them)

| Mistake | Why it's wrong | The fix |
|---|---|---|
| Using `float` for prices | Lossy precision; can produce false opportunities | `decimal.Decimal` everywhere |
| `time.time()` in tests | Non-deterministic | Inject a clock; tests pass a fake clock |
| Catching `Exception` broadly | Hides bugs in normalization | Catch specific errors; let unknown errors crash and be logged |
| Publishing `recovery=True` snapshots silently | Strategy may not realize data is stale-replacement | Strategy must filter or weight recovery snapshots explicitly |
| One reconnect retry then giving up | Causes outages from transient blips | Backoff with cap; alert only after sustained failure |

---

## When to Update This Skill

- The bus interface changes (rare — would propagate everywhere)
- A new exchange's WebSocket protocol requires a generalization
- A new QA scenario touches ingestion
