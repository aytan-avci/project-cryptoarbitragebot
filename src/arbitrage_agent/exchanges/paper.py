"""`PaperExchange` — simulated venue, no real money.

First adapter implemented (per `skills/exchange-integration/SKILL.md`).
Satisfies the `ExchangeAdapter` Protocol.

Scope evolved:
- Faz 5a — `fetch_book_snapshot` + `place_order(approved)` returning `OrderId`.
- Faz 6 — `place_order` ALSO records a synthetic `Fill` at the intent's
  limit price; `fetch_fills(since)` returns matching fills. This gives
  end-to-end visibility (opportunity → decision → order → fill → log)
  without yet modelling partial fills or order-book walking — those land
  in Faz 7 alongside ingestion depth and the hedger.
- `subscribe` and `cancel_order` and `fetch_balance` still raise
  `NotImplementedError` (Faz 7+).
"""

from dataclasses import replace
from datetime import datetime
from decimal import Decimal

from arbitrage_agent.domain import (
    Asset,
    ExchangeId,
    Fill,
    MarketSnapshot,
    OrderId,
    OrderIntent,
    Price,
    RiskDecision,
    Symbol,
    Volume,
    new_order_id,
    now_utc,
)
from arbitrage_agent.exchanges.base import SnapshotCallback


class PaperExchange:
    """Static-price simulated venue. `name` defaults to `"paper"` but the
    registry may override it. `taker_fee_bps` mirrors the strategy's fee
    assumption so realised P&L matches expected."""

    def __init__(
        self,
        prices: dict[Symbol, MarketSnapshot] | None = None,
        name: str = "paper",
        taker_fee_bps: int = 10,
    ) -> None:
        self._id: ExchangeId = ExchangeId(name)
        self._prices: dict[Symbol, MarketSnapshot] = dict(prices or {})
        self._fee_rate = Decimal(taker_fee_bps) / Decimal(10_000)
        self._fills: list[Fill] = []

    # ---- ExchangeAdapter protocol ---------------------------------------

    @property
    def id(self) -> ExchangeId:
        return self._id

    async def fetch_book_snapshot(self, symbol: Symbol) -> MarketSnapshot:
        base = self._prices.get(symbol)
        if base is None:
            raise KeyError(
                f"PaperExchange({self._id!r}) has no price for {symbol}"
            )
        return replace(base, timestamp_utc=now_utc())

    async def place_order(
        self, intent: OrderIntent, decision: RiskDecision
    ) -> OrderId:
        if not decision.approved:
            raise ValueError(
                f"PaperExchange.place_order requires approved decision; "
                f"got approved={decision.approved!r}, reason={decision.reason!r}"
            )
        order_id = new_order_id()
        # Paper-trade fill model: instant fill at the intent's limit price.
        # Order-book walk + slippage realism lands in Faz 7 when ingestion
        # exposes depth.
        fee = Price(intent.limit_price * intent.quantity * self._fee_rate)
        self._fills.append(
            Fill(
                opportunity_id=decision.opportunity_id,
                exchange=self._id,
                symbol=intent.symbol,
                side=intent.side,
                price=intent.limit_price,
                volume=intent.quantity,
                fee=fee,
                timestamp_utc=now_utc(),
            )
        )
        return order_id

    async def fetch_fills(self, since: datetime) -> list[Fill]:
        return [f for f in self._fills if f.timestamp_utc >= since]

    async def subscribe(
        self, symbols: list[Symbol], on_snapshot: SnapshotCallback
    ) -> None:
        raise NotImplementedError("PaperExchange.subscribe — Faz 7+")

    async def cancel_order(self, order_id: OrderId) -> None:
        """No-op: PaperExchange fills are instant + synthetic, so by the
        time the hedger calls cancel, nothing is outstanding. Accepting
        the call (instead of raising) lets the Faz 7g-c hedger's
        best-effort cancel loop traverse mixed paper/live adapter sets
        without special-casing."""
        return None

    async def fetch_balance(self, asset: Asset) -> Volume:
        raise NotImplementedError("PaperExchange.fetch_balance — Faz 7+")

    # ---- Test/setup convenience ----------------------------------------

    def set_price(self, snapshot: MarketSnapshot) -> None:
        """Seed or replace the static-table entry for a symbol."""
        self._prices[snapshot.symbol] = snapshot
