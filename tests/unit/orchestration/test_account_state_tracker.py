"""AccountStateTracker — stateful orchestration-side bookkeeping for risk gate."""

from decimal import Decimal

from arbitrage_agent.domain import (
    ExchangeId,
    Fill,
    MarketSnapshot,
    OrderIntent,
    Symbol,
    new_opportunity_id,
    now_utc,
    price,
    volume,
)
from arbitrage_agent.domain import Symbol as _Symbol  # noqa — already imported above
from arbitrage_agent.orchestration.account_state_tracker import AccountStateTracker


BTC = Symbol("BTC", "USDT")
BINANCE = ExchangeId("binance")
BYBIT = ExchangeId("bybit")


def _snap(exchange: ExchangeId, bid: str = "60000", ask: str = "60001") -> MarketSnapshot:
    return MarketSnapshot(
        exchange=exchange, symbol=BTC,
        bid=price(bid), ask=price(ask),
        bid_size=volume("1"), ask_size=volume("1"),
        timestamp_utc=now_utc(),
    )


def _fill(exchange: ExchangeId, side: str, qty: str) -> Fill:
    return Fill(
        opportunity_id=new_opportunity_id(),
        exchange=exchange, symbol=BTC, side=side,
        price=price("60000"), volume=volume(qty),
        fee=price("0.06"), timestamp_utc=now_utc(),
    )


def _intent(exchange: ExchangeId, side: str, qty: str = "0.001") -> OrderIntent:
    return OrderIntent(
        exchange=exchange, symbol=BTC, side=side,
        quantity=volume(qty), limit_price=price("60000"),
    )


# ---- Empty / default state -----------------------------------------------


def test_empty_tracker_returns_empty_state():
    t = AccountStateTracker()
    s = t.snapshot(now_ms=1_000_000_000_000)
    assert s.cash_by_exchange == {}
    assert s.open_position_qty == {}
    assert s.kill_switch_engaged is False
    assert s.recent_order_timestamps_ms == ()
    assert s.last_snapshot_age_ms_by_venue == {}


# ---- Position accumulation -----------------------------------------------


def test_buy_increases_position():
    t = AccountStateTracker()
    t.on_fill(_fill(BINANCE, "buy", "0.5"))
    s = t.snapshot(0)
    assert s.open_position_qty[(BINANCE, BTC)] == Decimal("0.5")


def test_sell_decreases_position():
    t = AccountStateTracker()
    t.on_fill(_fill(BINANCE, "sell", "0.3"))
    s = t.snapshot(0)
    assert s.open_position_qty[(BINANCE, BTC)] == Decimal("-0.3")


def test_buy_then_sell_nets():
    t = AccountStateTracker()
    t.on_fill(_fill(BINANCE, "buy", "1.0"))
    t.on_fill(_fill(BINANCE, "sell", "0.4"))
    s = t.snapshot(0)
    assert s.open_position_qty[(BINANCE, BTC)] == Decimal("0.6")


def test_per_venue_position_isolation():
    t = AccountStateTracker()
    t.on_fill(_fill(BINANCE, "buy", "0.5"))
    t.on_fill(_fill(BYBIT, "sell", "0.5"))
    s = t.snapshot(0)
    assert s.open_position_qty[(BINANCE, BTC)] == Decimal("0.5")
    assert s.open_position_qty[(BYBIT, BTC)] == Decimal("-0.5")


# ---- Snapshot freshness --------------------------------------------------


def test_snapshot_age_computed_from_now():
    t = AccountStateTracker()
    snap = _snap(BINANCE)
    t.on_snapshot(snap)
    snap_ms = int(snap.timestamp_utc.timestamp() * 1000)
    state = t.snapshot(now_ms=snap_ms + 5000)
    assert state.last_snapshot_age_ms_by_venue[BINANCE] == 5000


def test_newer_snapshot_replaces_older():
    t = AccountStateTracker()
    older = _snap(BINANCE)
    t.on_snapshot(older)
    older_ms = int(older.timestamp_utc.timestamp() * 1000)
    # Newer snapshot 2 s later
    import time
    time.sleep(0.001)  # ensure timestamps differ
    newer = _snap(BINANCE)
    t.on_snapshot(newer)
    newer_ms = int(newer.timestamp_utc.timestamp() * 1000)
    s = t.snapshot(now_ms=newer_ms + 1000)
    assert s.last_snapshot_age_ms_by_venue[BINANCE] == 1000


def test_out_of_order_snapshot_does_not_regress():
    """If an older frame arrives after a newer one, freshness stays at
    the newer timestamp."""
    t = AccountStateTracker()
    newer = _snap(BINANCE)
    t.on_snapshot(newer)
    newer_ms = int(newer.timestamp_utc.timestamp() * 1000)
    # Simulate an older frame
    from datetime import timedelta
    older_ts = newer.timestamp_utc - timedelta(seconds=10)
    older = MarketSnapshot(
        exchange=BINANCE, symbol=BTC,
        bid=price("60000"), ask=price("60001"),
        bid_size=volume("1"), ask_size=volume("1"),
        timestamp_utc=older_ts,
    )
    t.on_snapshot(older)
    s = t.snapshot(now_ms=newer_ms + 500)
    assert s.last_snapshot_age_ms_by_venue[BINANCE] == 500


# ---- Order timestamps deque ----------------------------------------------


def test_on_order_submitted_records_timestamp():
    t = AccountStateTracker()
    t.on_order_submitted(when_ms=12345, leg_count=2)
    s = t.snapshot(0)
    assert s.recent_order_timestamps_ms == (12345, 12345)


def test_on_intent_submitted_per_leg():
    t = AccountStateTracker()
    intents = [_intent(BINANCE, "buy"), _intent(BYBIT, "sell")]
    t.on_intent_submitted(intents, when_ms=999)
    s = t.snapshot(0)
    assert s.recent_order_timestamps_ms == (999, 999)


def test_order_deque_capped():
    """The retained-order deque has a hard cap so long sessions don't
    leak memory."""
    t = AccountStateTracker()
    cap = AccountStateTracker._MAX_RETAINED_ORDER_TS
    for i in range(cap + 100):
        t.on_order_submitted(when_ms=i)
    s = t.snapshot(0)
    assert len(s.recent_order_timestamps_ms) == cap
    # Newest entries retained
    assert s.recent_order_timestamps_ms[-1] == cap + 99


# ---- Kill switch ---------------------------------------------------------


def test_kill_switch_flows_to_snapshot():
    t = AccountStateTracker()
    t.set_kill_switch(True)
    assert t.snapshot(0).kill_switch_engaged is True
    t.set_kill_switch(False)
    assert t.snapshot(0).kill_switch_engaged is False


# ---- Faz 7g-a — daily P&L --------------------------------------------------


class TestDailyPnl:
    def test_empty_tracker_zero_pnl(self):
        t = AccountStateTracker()
        assert t.daily_pnl_usd == Decimal("0")
        assert t.daily_pnl_day is None

    def test_sell_increases_pnl(self):
        t = AccountStateTracker()
        # Sell 0.001 BTC at 60000 with fee 0.06 → +60.00 - 0.06 = 59.94
        t.on_fill(_fill(BINANCE, "sell", "0.001"))
        assert t.daily_pnl_usd == Decimal("59.94")

    def test_buy_decreases_pnl(self):
        t = AccountStateTracker()
        # Buy 0.001 at 60000 fee 0.06 → -60.00 - 0.06 = -60.06
        t.on_fill(_fill(BINANCE, "buy", "0.001"))
        assert t.daily_pnl_usd == Decimal("-60.06")

    def test_buy_then_sell_nets_cost_of_fees(self):
        """Buy and sell same qty same price: -60 - 0.06 + 60 - 0.06 = -0.12."""
        t = AccountStateTracker()
        t.on_fill(_fill(BINANCE, "buy", "0.001"))
        t.on_fill(_fill(BINANCE, "sell", "0.001"))
        assert t.daily_pnl_usd == Decimal("-0.12")

    def test_arb_profit_accumulates(self):
        """Spatial-arb-ish: buy at 60000, sell at 60800. Net per pair:
        +60.80 - 60 - 0.06 - 0.06 = +0.68."""
        t = AccountStateTracker()
        buy_fill = _fill(BINANCE, "buy", "0.001")
        sell_fill = Fill(
            opportunity_id=new_opportunity_id(),
            exchange=BYBIT, symbol=BTC, side="sell",
            price=price("60800"), volume=volume("0.001"),
            fee=price("0.06"), timestamp_utc=now_utc(),
        )
        t.on_fill(buy_fill)
        t.on_fill(sell_fill)
        assert t.daily_pnl_usd == Decimal("0.68")

    def test_day_rollover_resets(self):
        """A fill timestamped on a new UTC day resets the daily counter."""
        from datetime import datetime, timezone
        t = AccountStateTracker()
        # Day 1 — loss
        day1 = datetime(2026, 1, 1, 23, 59, 0, tzinfo=timezone.utc)
        t.on_fill(Fill(
            opportunity_id=new_opportunity_id(),
            exchange=BINANCE, symbol=BTC, side="buy",
            price=price("60000"), volume=volume("0.001"),
            fee=price("0.06"), timestamp_utc=day1,
        ))
        assert t.daily_pnl_day == "2026-01-01"
        assert t.daily_pnl_usd < 0
        # Day 2 — small profit fill
        day2 = datetime(2026, 1, 2, 0, 0, 1, tzinfo=timezone.utc)
        t.on_fill(Fill(
            opportunity_id=new_opportunity_id(),
            exchange=BINANCE, symbol=BTC, side="sell",
            price=price("60000"), volume=volume("0.001"),
            fee=price("0.06"), timestamp_utc=day2,
        ))
        # Day 1's loss is forgotten; day 2 stands alone.
        assert t.daily_pnl_day == "2026-01-02"
        assert t.daily_pnl_usd == Decimal("59.94")


class TestSetCash:
    def test_default_no_cash(self):
        assert AccountStateTracker().snapshot(0).cash_by_exchange == {}

    def test_set_cash_flows_to_snapshot(self):
        from decimal import Decimal
        t = AccountStateTracker()
        t.set_cash(BINANCE, Decimal("1000.50"))
        t.set_cash(BYBIT, Decimal("250.00"))
        s = t.snapshot(0)
        assert s.cash_by_exchange[BINANCE] == Decimal("1000.50")
        assert s.cash_by_exchange[BYBIT] == Decimal("250.00")
