"""Triangular arbitrage — three-leg cycle within one exchange (Faz (B)).

Per `skills/arbitrage-detection/SKILL.md § Triangular Arbitrage`:

> Inputs: top of book for three pairs on one exchange that form a
> cycle, e.g., (USDT/BTC, BTC/ETH, ETH/USDT).
> Action: trade the cycle and check that 1 unit of starting asset
> comes back as > 1 unit after all three legs and fees.
> Edge condition: all three legs must fill near-simultaneously or
> exposure builds up. Strategy emits the full cycle as one
> Opportunity; execution module decides whether to issue them as
> IOC orders or use a venue feature like atomic batch orders.

The cycle is parameterised by three assets:

* `quote` — the starting+ending currency (e.g. `USDT`).
* `intermediate` — the bridge currency (e.g. `BTC`).
* `base` — the third currency (e.g. `ETH`).

Three pairs are needed on the same venue:

* `intermediate/quote`  e.g. `BTC/USDT`
* `base/quote`          e.g. `ETH/USDT`
* `base/intermediate`   e.g. `ETH/BTC`

Two cyclic paths are evaluated each tick:

* **Forward**  `Q → I → B → Q`
  1. buy `I` paying `Q` at `intermediate/quote` ask
  2. buy `B` paying `I` at `base/intermediate` ask
  3. sell `B` receiving `Q` at `base/quote` bid

* **Reverse**  `Q → B → I → Q`
  1. buy `B` paying `Q` at `base/quote` ask
  2. sell `B` receiving `I` at `base/intermediate` bid
  3. sell `I` receiving `Q` at `intermediate/quote` bid

Net profit accounts for the per-leg taker fee on every hop
(`taker_fee_bps / 10_000`). The strategy emits the better of the
two paths if its profit clears `min_profit_threshold_usd`, else
`None`. Slippage realism (order-book walk) lands when ingestion
exposes depth — same TODO as the spatial strategy.

PURE: no I/O, no `time.now()`, clock injected.
"""

from datetime import datetime, timezone
from decimal import Decimal

from arbitrage_agent.domain import (
    Asset,
    ExchangeId,
    Opportunity,
    OrderIntent,
    Price,
    StrategyName,
    Symbol,
    Volume,
    new_opportunity_id,
    price,
    volume,
)
from arbitrage_agent.strategies.base import Clock, MarketView


class TriangularArbitrage:
    """Single-venue triangular arbitrage."""

    name: StrategyName = "triangular"

    def __init__(
        self,
        exchange: ExchangeId,
        quote: Asset,
        intermediate: Asset,
        base: Asset,
        size_quote: Decimal,
        taker_fee_bps: int = 10,
        min_profit_threshold_usd: Decimal = Decimal("0.50"),
        valid_for_ms: int = 1000,
        confidence: float = 0.85,
    ) -> None:
        self._exchange = exchange
        self._quote = quote
        self._intermediate = intermediate
        self._base = base
        self._size_quote = size_quote
        self._fee_rate = Decimal(taker_fee_bps) / Decimal(10_000)
        self._min_profit = min_profit_threshold_usd
        self._valid_for_ms = valid_for_ms
        self._confidence = confidence

    # ---- Symbol resolution ---------------------------------------------

    @property
    def _sym_iq(self) -> Symbol:
        """intermediate/quote  (e.g. BTC/USDT)"""
        return Symbol(self._intermediate, self._quote)

    @property
    def _sym_bq(self) -> Symbol:
        """base/quote  (e.g. ETH/USDT)"""
        return Symbol(self._base, self._quote)

    @property
    def _sym_bi(self) -> Symbol:
        """base/intermediate  (e.g. ETH/BTC)"""
        return Symbol(self._base, self._intermediate)

    # ---- Strategy protocol ----------------------------------------------

    @property
    def symbols(self) -> list[Symbol]:
        return [self._sym_iq, self._sym_bq, self._sym_bi]

    @property
    def min_venues(self) -> int:
        return 1

    def evaluate(self, view: MarketView, clock: Clock) -> Opportunity | None:
        snap_iq = view.snapshot(self._exchange, self._sym_iq)
        snap_bq = view.snapshot(self._exchange, self._sym_bq)
        snap_bi = view.snapshot(self._exchange, self._sym_bi)
        if snap_iq is None or snap_bq is None or snap_bi is None:
            return None

        keep = Decimal("1") - self._fee_rate

        # ---- Forward path: Q → I → B → Q -------------------------------
        ask_iq = Decimal(snap_iq.ask)
        ask_bi = Decimal(snap_bi.ask)
        bid_bq = Decimal(snap_bq.bid)
        qty_i_fwd = (self._size_quote / ask_iq) * keep
        qty_b_fwd = (qty_i_fwd / ask_bi) * keep
        quote_out_fwd = (qty_b_fwd * bid_bq) * keep
        profit_fwd = quote_out_fwd - self._size_quote

        # ---- Reverse path: Q → B → I → Q -------------------------------
        ask_bq = Decimal(snap_bq.ask)
        bid_bi = Decimal(snap_bi.bid)
        bid_iq = Decimal(snap_iq.bid)
        qty_b_rev = (self._size_quote / ask_bq) * keep
        qty_i_rev = (qty_b_rev * bid_bi) * keep
        quote_out_rev = (qty_i_rev * bid_iq) * keep
        profit_rev = quote_out_rev - self._size_quote

        # ---- Pick the better path --------------------------------------
        if profit_fwd >= profit_rev:
            profit = profit_fwd
            legs = self._forward_legs(
                qty_i_fwd, qty_b_fwd, ask_iq, ask_bi, bid_bq,
            )
        else:
            profit = profit_rev
            legs = self._reverse_legs(
                qty_b_rev, qty_i_rev, ask_bq, bid_bi, bid_iq,
            )

        if profit < self._min_profit:
            return None

        detected_at = datetime.fromtimestamp(
            clock.now_ms() / 1000, tz=timezone.utc
        )
        return Opportunity(
            id=new_opportunity_id(),
            detected_at=detected_at,
            strategy=self.name,
            legs=legs,
            expected_net_profit=profit,
            confidence=self._confidence,
            valid_for_ms=self._valid_for_ms,
        )

    # ---- Internals ------------------------------------------------------

    def _forward_legs(
        self,
        qty_intermediate: Decimal,
        qty_base: Decimal,
        ask_iq: Decimal,
        ask_bi: Decimal,
        bid_bq: Decimal,
    ) -> tuple[OrderIntent, OrderIntent, OrderIntent]:
        """Q → I → B → Q. Quantities are pre-fee — i.e. the amount the
        leg ATTEMPTS to acquire; the venue then nets the fee."""
        return (
            OrderIntent(
                exchange=self._exchange, symbol=self._sym_iq, side="buy",
                quantity=_vol(qty_intermediate), limit_price=_px(ask_iq),
            ),
            OrderIntent(
                exchange=self._exchange, symbol=self._sym_bi, side="buy",
                quantity=_vol(qty_base), limit_price=_px(ask_bi),
            ),
            OrderIntent(
                exchange=self._exchange, symbol=self._sym_bq, side="sell",
                quantity=_vol(qty_base), limit_price=_px(bid_bq),
            ),
        )

    def _reverse_legs(
        self,
        qty_base: Decimal,
        qty_intermediate: Decimal,
        ask_bq: Decimal,
        bid_bi: Decimal,
        bid_iq: Decimal,
    ) -> tuple[OrderIntent, OrderIntent, OrderIntent]:
        """Q → B → I → Q."""
        return (
            OrderIntent(
                exchange=self._exchange, symbol=self._sym_bq, side="buy",
                quantity=_vol(qty_base), limit_price=_px(ask_bq),
            ),
            OrderIntent(
                exchange=self._exchange, symbol=self._sym_bi, side="sell",
                quantity=_vol(qty_base), limit_price=_px(bid_bi),
            ),
            OrderIntent(
                exchange=self._exchange, symbol=self._sym_iq, side="sell",
                quantity=_vol(qty_intermediate), limit_price=_px(bid_iq),
            ),
        )


# ---- Small typing helpers -------------------------------------------------


def _vol(d: Decimal) -> Volume:
    return volume(str(d))


def _px(d: Decimal) -> Price:
    return price(str(d))
