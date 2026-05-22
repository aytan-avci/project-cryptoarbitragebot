"""Mutable orchestration-side state that the risk gate reads via
`AccountState` snapshots.

The risk gate is pure (no I/O, no mutation). The orchestrator owns the
stateful side: positions accumulate from fills, recent order timestamps
form a rolling window for the orders/min check, the most-recent snapshot
timestamp per venue feeds the freshness check.

Snapshot generation (`snapshot(now_ms)`) is the only handoff to the
gate; everything else (fills, orders, snapshots, kill-switch state)
flows in via the four `on_*` methods.
"""

from collections import deque
from decimal import Decimal
from typing import Deque

from arbitrage_agent.domain import (
    ExchangeId,
    Fill,
    MarketSnapshot,
    OrderIntent,
    Symbol,
    Volume,
    volume,
)
from arbitrage_agent.risk.limits import AccountState


class AccountStateTracker:
    """Single-process state, in-memory. One instance per pipeline run."""

    # Hard cap on retained order timestamps so the deque cannot grow
    # without bound across long-running sessions.
    _MAX_RETAINED_ORDER_TS = 10_000

    def __init__(self) -> None:
        self._positions: dict[tuple[ExchangeId, Symbol], Decimal] = {}
        self._cash: dict[ExchangeId, Decimal] = {}
        self._order_timestamps_ms: Deque[int] = deque(
            maxlen=self._MAX_RETAINED_ORDER_TS
        )
        self._last_snapshot_ms_by_venue: dict[ExchangeId, int] = {}
        self._kill_switch_engaged = False
        # Faz 7g-a — daily realised P&L (UTC day boundary)
        self._daily_pnl_usd: Decimal = Decimal("0")
        self._daily_pnl_day: str | None = None  # 'YYYY-MM-DD' UTC

    # ---- Update inputs --------------------------------------------------

    def on_snapshot(self, snap: MarketSnapshot) -> None:
        ts_ms = int(snap.timestamp_utc.timestamp() * 1000)
        prev = self._last_snapshot_ms_by_venue.get(snap.exchange)
        # Keep the most recent — out-of-order frames don't move the
        # freshness needle backwards.
        if prev is None or ts_ms > prev:
            self._last_snapshot_ms_by_venue[snap.exchange] = ts_ms

    def on_fill(self, fill: Fill) -> None:
        # Position delta
        key = (fill.exchange, fill.symbol)
        signed_volume = Decimal(str(fill.volume))
        if fill.side == "sell":
            signed_volume = -signed_volume
        self._positions[key] = self._positions.get(key, Decimal("0")) + signed_volume

        # Realised daily P&L (Faz 7g-a). UTC day rollover resets the counter.
        fill_day = fill.timestamp_utc.strftime("%Y-%m-%d")
        if self._daily_pnl_day is None or fill_day != self._daily_pnl_day:
            self._daily_pnl_usd = Decimal("0")
            self._daily_pnl_day = fill_day
        sign = Decimal("1") if fill.side == "sell" else Decimal("-1")
        cash_flow = sign * Decimal(str(fill.price)) * Decimal(str(fill.volume))
        # Fee is always a cost regardless of side.
        self._daily_pnl_usd += cash_flow - Decimal(str(fill.fee))

    @property
    def daily_pnl_usd(self) -> Decimal:
        """Realised P&L for the current UTC day; resets at midnight UTC
        on the first fill of the next day."""
        return self._daily_pnl_usd

    @property
    def daily_pnl_day(self) -> str | None:
        return self._daily_pnl_day

    def on_order_submitted(self, when_ms: int, leg_count: int = 1) -> None:
        for _ in range(leg_count):
            self._order_timestamps_ms.append(when_ms)

    def on_intent_submitted(
        self, intents: list[OrderIntent], when_ms: int
    ) -> None:
        """Bulk helper — record a submission per leg."""
        self.on_order_submitted(when_ms, leg_count=len(intents))

    def set_kill_switch(self, engaged: bool) -> None:
        self._kill_switch_engaged = engaged

    def set_cash(self, exchange: ExchangeId, amount: Decimal) -> None:
        """Optional — paper smoke runs don't populate cash; live
        adapters (Faz 7g) feed this via balance polling."""
        self._cash[exchange] = amount

    # ---- Output ---------------------------------------------------------

    def snapshot(self, now_ms: int) -> AccountState:
        ages = {
            ex: now_ms - ts
            for ex, ts in self._last_snapshot_ms_by_venue.items()
        }
        positions_as_volume = {
            key: volume(str(qty))
            for key, qty in self._positions.items()
        }
        return AccountState(
            cash_by_exchange=dict(self._cash),
            open_position_qty=positions_as_volume,
            kill_switch_engaged=self._kill_switch_engaged,
            recent_order_timestamps_ms=tuple(self._order_timestamps_ms),
            last_snapshot_age_ms_by_venue=ages,
        )
