"""Spatial (cross-exchange) arbitrage.

Per `skills/arbitrage-detection/SKILL.md § Spatial Arbitrage`: compare
top-of-book on the same `Symbol` across two venues; buy on the cheaper
ask, sell on the richer bid, iff `expected_net_profit` after fees +
slippage clears `min_profit_threshold`.

Faz 5c scope:
- Two fixed venues + one symbol per `SpatialArbitrage` instance.
- Fee model: flat taker bps per leg (operator-tunable via Settings).
- Slippage model: constant absolute USD per leg (order-book walk lands
  in Faz 6 when ingestion exposes depth).

The class satisfies `Strategy` protocol structurally. PURE: no I/O, no
`time` — clock is injected.
"""

from datetime import datetime, timezone
from decimal import Decimal

from arbitrage_agent.domain import (
    ExchangeId,
    MarketSnapshot,
    Opportunity,
    OrderIntent,
    Price,
    StrategyName,
    Symbol,
    Volume,
    new_opportunity_id,
)
from arbitrage_agent.strategies.base import Clock, MarketView


class SpatialArbitrage:
    """Two-venue spatial arbitrage strategy."""

    name: StrategyName = "spatial"

    def __init__(
        self,
        symbol: Symbol,
        exchange_a: ExchangeId,
        exchange_b: ExchangeId,
        size: Volume,
        taker_fee_bps: int = 10,
        slippage_usd_per_leg: Decimal = Decimal("0.01"),
        min_profit_threshold_usd: Decimal = Decimal("0.50"),
        valid_for_ms: int = 1000,
        confidence: float = 0.9,
    ) -> None:
        self._symbol = symbol
        self._a = exchange_a
        self._b = exchange_b
        self._size = size
        self._fee_rate = Decimal(taker_fee_bps) / Decimal(10_000)
        self._slippage_per_leg = slippage_usd_per_leg
        self._min_profit = min_profit_threshold_usd
        self._valid_for_ms = valid_for_ms
        self._confidence = confidence

    # ---- Strategy protocol ---------------------------------------------

    def evaluate(self, view: MarketView, clock: Clock) -> Opportunity | None:
        snap_a = view.snapshot(self._a, self._symbol)
        snap_b = view.snapshot(self._b, self._symbol)
        if snap_a is None or snap_b is None:
            return None

        best = self._best_direction(snap_a, snap_b)
        if best is None:
            return None
        buy_exchange, buy_price, sell_exchange, sell_price = best

        net_profit = self._net_profit(buy_price, sell_price)
        if net_profit < self._min_profit:
            return None

        buy_leg = OrderIntent(
            exchange=buy_exchange,
            symbol=self._symbol,
            side="buy",
            quantity=self._size,
            limit_price=buy_price,
        )
        sell_leg = OrderIntent(
            exchange=sell_exchange,
            symbol=self._symbol,
            side="sell",
            quantity=self._size,
            limit_price=sell_price,
        )

        detected_at = datetime.fromtimestamp(
            clock.now_ms() / 1000, tz=timezone.utc
        )
        return Opportunity(
            id=new_opportunity_id(),
            detected_at=detected_at,
            strategy=self.name,
            legs=(buy_leg, sell_leg),  # buy first (Faz 5c open Q (e))
            expected_net_profit=net_profit,
            confidence=self._confidence,
            valid_for_ms=self._valid_for_ms,
        )

    # ---- Internals (pure helpers) --------------------------------------

    def _best_direction(
        self, snap_a: MarketSnapshot, snap_b: MarketSnapshot
    ) -> tuple[ExchangeId, Price, ExchangeId, Price] | None:
        """Pick the more profitable direction by gross-per-unit spread.

        Returns (buy_exchange, buy_price, sell_exchange, sell_price) or
        None if neither direction is gross-positive.
        """
        d1_gross = snap_b.bid - snap_a.ask  # buy A ask, sell B bid
        d2_gross = snap_a.bid - snap_b.ask  # buy B ask, sell A bid
        if d1_gross > 0 and d1_gross >= d2_gross:
            return (self._a, snap_a.ask, self._b, snap_b.bid)
        if d2_gross > 0:
            return (self._b, snap_b.ask, self._a, snap_a.bid)
        return None

    def _net_profit(self, buy_price: Price, sell_price: Price) -> Decimal:
        """Gross spread × size minus per-leg fees minus per-leg slippage."""
        gross = (sell_price - buy_price) * self._size
        fees = (buy_price + sell_price) * self._size * self._fee_rate
        slippage = self._slippage_per_leg * Decimal(2)
        return Decimal(gross) - Decimal(fees) - slippage
