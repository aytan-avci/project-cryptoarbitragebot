"""SpatialArbitrage tests — pure-function strategy with synthetic snapshots."""

from decimal import Decimal

from arbitrage_agent.domain import (
    ExchangeId,
    MarketSnapshot,
    Symbol,
    now_utc,
    price,
    volume,
)
from arbitrage_agent.ingestion.bus import LatestSnapshotView
from arbitrage_agent.strategies.base import Strategy
from arbitrage_agent.strategies.spatial import SpatialArbitrage


class _FixedClock:
    """Test double for `Clock`. Pure; returns the same `now_ms` each call."""

    def __init__(self, now_ms: int) -> None:
        self._now_ms = now_ms

    def now_ms(self) -> int:
        return self._now_ms


def _snap(exchange: str, bid: str, ask: str) -> MarketSnapshot:
    return MarketSnapshot(
        exchange=ExchangeId(exchange),
        symbol=Symbol("BTC", "USDT"),
        bid=price(bid),
        ask=price(ask),
        bid_size=volume("10"),
        ask_size=volume("10"),
        timestamp_utc=now_utc(),
    )


def _build_view(*snapshots: MarketSnapshot) -> LatestSnapshotView:
    v = LatestSnapshotView()
    for s in snapshots:
        v.update(s)
    return v


def _strategy(**overrides) -> SpatialArbitrage:
    base = dict(
        symbol=Symbol("BTC", "USDT"),
        exchange_a=ExchangeId("binance"),
        exchange_b=ExchangeId("bybit"),
        size=volume("0.01"),
        taker_fee_bps=10,                        # 0.10 %
        slippage_usd_per_leg=Decimal("0.01"),
        min_profit_threshold_usd=Decimal("0.50"),
        valid_for_ms=1000,
        confidence=0.9,
    )
    base.update(overrides)
    return SpatialArbitrage(**base)


# ---------- Protocol conformance --------------------------------------------

def test_satisfies_strategy_protocol():
    assert isinstance(_strategy(), Strategy)


def test_name_is_spatial_literal():
    assert _strategy().name == "spatial"


# ---------- Happy paths -----------------------------------------------------

class TestHappyPath:
    def test_emits_opportunity_when_spread_clears_costs(self):
        """binance: 60_000/60_001 ; bybit: 60_200/60_201
        → buy on binance at 60_001, sell on bybit at 60_200.
        per-unit gross = 199; size 0.01 → 1.99 USD
        fees ≈ (60_001+60_200) × 0.01 × 0.001 = 1.2020
        slippage = 0.02
        net ≈ 0.768 USD > 0.50 threshold."""
        view = _build_view(
            _snap("binance", bid="60000", ask="60001"),
            _snap("bybit",   bid="60200", ask="60201"),
        )
        opp = _strategy().evaluate(view, _FixedClock(1_700_000_000_000))
        assert opp is not None
        assert opp.strategy == "spatial"
        assert len(opp.legs) == 2
        assert opp.legs[0].side == "buy"   # (e) buy first
        assert opp.legs[1].side == "sell"
        assert opp.legs[0].exchange == "binance"
        assert opp.legs[1].exchange == "bybit"
        assert opp.expected_net_profit > Decimal("0.50")
        assert opp.confidence == 0.9
        assert opp.valid_for_ms == 1000

    def test_picks_better_direction_when_reversed(self):
        """Reverse the venues — buy on bybit, sell on binance."""
        view = _build_view(
            _snap("binance", bid="60200", ask="60201"),
            _snap("bybit",   bid="60000", ask="60001"),
        )
        opp = _strategy().evaluate(view, _FixedClock(0))
        assert opp is not None
        assert opp.legs[0].exchange == "bybit"      # buy cheap
        assert opp.legs[1].exchange == "binance"    # sell rich

    def test_detected_at_uses_injected_clock(self):
        view = _build_view(
            _snap("binance", bid="60000", ask="60001"),
            _snap("bybit",   bid="60200", ask="60201"),
        )
        now_ms = 1_700_000_000_000  # 2023-11-14T22:13:20Z
        opp = _strategy().evaluate(view, _FixedClock(now_ms))
        assert opp is not None
        assert int(opp.detected_at.timestamp() * 1000) == now_ms


# ---------- Rejections ------------------------------------------------------

class TestRejections:
    def test_no_opportunity_when_gross_negative(self):
        # Both venues quote roughly the same — no profitable direction
        view = _build_view(
            _snap("binance", bid="60000", ask="60001"),
            _snap("bybit",   bid="60000", ask="60001"),
        )
        assert _strategy().evaluate(view, _FixedClock(0)) is None

    def test_no_opportunity_when_below_threshold(self):
        """Tiny gap that fees + slippage eat through.

        gross = (60_010 - 60_001) × 0.01 = 0.09 USD; fees + slippage dwarf it.
        """
        view = _build_view(
            _snap("binance", bid="60000", ask="60001"),
            _snap("bybit",   bid="60010", ask="60011"),
        )
        assert _strategy().evaluate(view, _FixedClock(0)) is None

    def test_no_opportunity_when_one_venue_missing(self):
        view = _build_view(_snap("binance", bid="60000", ask="60001"))
        assert _strategy().evaluate(view, _FixedClock(0)) is None

    def test_no_opportunity_when_view_empty(self):
        assert _strategy().evaluate(LatestSnapshotView(), _FixedClock(0)) is None

    def test_higher_min_profit_threshold_rejects(self):
        """Same setup as happy path, but raise the threshold above the
        computed net (≈0.77 USD). Strategy returns None."""
        view = _build_view(
            _snap("binance", bid="60000", ask="60001"),
            _snap("bybit",   bid="60200", ask="60201"),
        )
        strict = _strategy(min_profit_threshold_usd=Decimal("100"))
        assert strict.evaluate(view, _FixedClock(0)) is None


# ---------- Purity guarantees ----------------------------------------------

class TestPurity:
    def test_same_inputs_same_outputs(self):
        view = _build_view(
            _snap("binance", bid="60000", ask="60001"),
            _snap("bybit",   bid="60200", ask="60201"),
        )
        clock = _FixedClock(42_000_000_000)
        s = _strategy()
        opp1 = s.evaluate(view, clock)
        opp2 = s.evaluate(view, clock)
        assert opp1 is not None and opp2 is not None
        # Different ids (UUID4) but same numeric content
        assert opp1.expected_net_profit == opp2.expected_net_profit
        assert opp1.detected_at == opp2.detected_at
        assert opp1.legs[0].limit_price == opp2.legs[0].limit_price
