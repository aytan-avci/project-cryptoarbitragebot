---
name: arbitrage-detection
description: Operating manual for the strategy engine — the module that decides when an arbitrage opportunity exists. Read this BEFORE writing any code under `src/arbitrage_agent/strategies/` or adding/modifying a strategy. Covers the Strategy protocol, the "pure function" rule, profitability math (including fees and slippage), and per-strategy specifics for spatial, triangular, and funding-rate arbitrage.
---

# SKILL · Arbitrage Detection (Strategy Engine)

## Purpose

Look at a market snapshot. Decide if an arbitrage is profitable **after all
costs**. If yes, emit an `Opportunity`. If no, return `None`.

The strategy engine is the **brain** of the system. It is also the
**simplest** module to test, because it has no I/O. Keep it that way.

---

## The Cardinal Rule: Strategies Are Pure Functions

```python
class Strategy(Protocol):
    name: StrategyName

    def evaluate(self, snapshot: MarketView, clock: Clock) -> Opportunity | None:
        """Pure. No I/O. No global state. Same input → same output, always."""
```

**What "pure" forbids:**

- `await` anything
- `time.time()`, `datetime.now()`, or any wall-clock read — clock is injected
- `requests`, `aiohttp`, anything that touches the network
- File I/O
- Mutable module-level state
- Random numbers without an injected seed

**Why?** QA-6.1 says strategy unit tests run in <50 ms with no I/O. QA-6.2
says replay must be deterministic. Both die the moment a strategy reads the
clock or makes an HTTP call.

If your strategy *needs* something time-varying (e.g., funding rate), it
must come in through the `MarketView` snapshot. Add the field; don't bypass
the rule.

---

## Profitability Math (FR-3)

A strategy must subtract **all** of these before declaring profit:

1. **Taker fees** on each leg (use the worst case — taker fees, not maker,
   unless the leg can be guaranteed to make).
2. **Slippage estimate** based on order book depth (walk the book for the
   intended size, compute the volume-weighted average price; subtract from
   the top-of-book price).
3. **Transfer cost** between exchanges (spatial only) or **gas** (DEX, out
   of MVP scope).
4. **Funding accrual** during the holding period (funding-rate strategy
   only — and it is the *profit source*, so signs matter).

Pseudocode for the spatial case:

```
buy_price_with_slip  = top_ask_A + slippage(book_A, size, side="buy")
sell_price_with_slip = top_bid_B - slippage(book_B, size, side="sell")

gross_spread = sell_price_with_slip - buy_price_with_slip
fees         = size * (buy_price_with_slip  * fee_A_taker
                     + sell_price_with_slip * fee_B_taker)

expected_net = size * gross_spread - fees   # transfer cost ignored if pre-funded

if expected_net > min_profit_threshold:
    emit Opportunity(...)
```

**Gross spread is never a trade signal.** "There's a $50 spread on BTC"
means nothing until you subtract fees and slippage.

---

## Strategy Specifics

### Spatial (cross-exchange) Arbitrage

- Inputs: top of book on the same `Symbol` across 2+ exchanges
- Action: buy on cheapest, sell on most expensive
- **Risk:** requires pre-funded balances on both exchanges. On-chain
  transfer to rebalance takes minutes-to-hours and erodes profit.
- **Edge condition:** if one venue's depth is insufficient for the
  desired size, downsize the opportunity to the lesser depth.

### Triangular Arbitrage

- Inputs: top of book for three pairs on **one** exchange that form a
  cycle, e.g., `(USDT/BTC, BTC/ETH, ETH/USDT)`.
- Action: trade the cycle and check that 1 unit of starting asset comes
  back as > 1 unit after all three legs and fees.
- **Edge condition:** all three legs must fill near-simultaneously or
  exposure builds up. Strategy emits the full cycle as one `Opportunity`;
  execution module decides whether to issue them as IOC orders or use a
  venue feature like atomic batch orders if available.

### Funding-Rate Arbitrage

- Inputs: funding rate of a perpetual contract + spot price + perp price
- Action: if funding rate is positive (longs pay shorts), short the perp
  and long the spot in equal size. Collect funding every period.
- **Why low-risk:** market-neutral. The position doesn't care if BTC
  pumps or dumps. But:
  - Exchange-specific risk (counterparty)
  - Funding rate flips can erase the edge
  - Liquidation risk on the perp side if margin is thin
- **Edge condition:** monitor funding rate continuously; close when rate
  no longer covers fees.

---

## The `Opportunity` Contract (output)

```python
@dataclass(frozen=True)
class Opportunity:
    id: OpportunityId                  # uuid; for traceability
    detected_at: datetime              # injected clock, UTC
    strategy: StrategyName
    legs: tuple[OrderIntent, ...]      # 2 for spatial, 3 for triangular, 2 for funding
    expected_net_profit: Decimal
    confidence: float                  # 0..1; how sure is the strategy?
    valid_for_ms: int                  # after which the opportunity is stale
```

The `expected_net_profit` is the **gate** — risk and execution downstream
trust this number. If a strategy lies (uses gross instead of net), the
whole system silently loses money.

---

## Thresholds & Tunable Parameters

All thresholds (`min_profit`, `min_confidence`, `min_size`, `valid_for_ms`)
**live in config**, not in code. The strategy reads them once at construction.

Why config? QA-5.3: the operator must be able to change thresholds without
a code change.

---

## Anti-Patterns

| Anti-pattern | What goes wrong |
|---|---|
| Reading `time.time()` to filter "stale" snapshots | Non-deterministic; replay breaks |
| Using `float` for prices in math | Tiny rounding errors fabricate opportunities; especially in triangular |
| Skipping the slippage calc because "size is small" | Production sizes grow; the bug bites later |
| Emitting opportunities without `expected_net_profit` field set | Risk module has no basis to decide |
| Putting fee rates as constants | Exchange fee changes silently break detection |
| Multi-strategy "OR" logic inside one strategy class | Two strategies; split them. (Karpathy 2.) |

---

## Testing Strategies

Each strategy has a `tests/unit/strategies/test_<name>.py` with at minimum:

- **Happy path:** synthetic snapshot with a known profitable gap → emits expected `Opportunity`
- **Below threshold:** snapshot with a gap smaller than fees → returns `None`
- **Insufficient depth:** large size, thin book → either downsized opportunity or `None`
- **Negative gap:** market is "wrong way" → `None`
- **Edge values:** zero prices, missing fields → `None` plus a logged warning (never crash)

Tests use hand-built `MarketView` objects. No `PaperExchange`, no
ingestion. Just the function and its inputs.

---

## When to Update This Skill

- A new strategy is added and has a profile that needs documenting here
- The `Strategy` protocol changes
- The profitability formula changes for an existing strategy (e.g., a new
  cost type is included)
