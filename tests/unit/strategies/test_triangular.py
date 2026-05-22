"""TriangularArbitrage tests — pure-function single-venue cycle (Faz (B))."""

from decimal import Decimal

from arbitrage_agent.domain import (
    Asset,
    ExchangeId,
    MarketSnapshot,
    Symbol,
    now_utc,
    price,
    volume,
)
from arbitrage_agent.ingestion.bus import LatestSnapshotView
from arbitrage_agent.strategies.base import Strategy
from arbitrage_agent.strategies.triangular import TriangularArbitrage


_BINANCE = ExchangeId("binance")


class _FixedClock:
    def __init__(self, now_ms: int = 1_700_000_000_000) -> None:
        self._now_ms = now_ms

    def now_ms(self) -> int:
        return self._now_ms


def _snap(base: str, quote: str, bid: str, ask: str,
          venue: ExchangeId = _BINANCE) -> MarketSnapshot:
    return MarketSnapshot(
        exchange=venue, symbol=Symbol(base, quote),
        bid=price(bid), ask=price(ask),
        bid_size=volume("100"), ask_size=volume("100"),
        timestamp_utc=now_utc(),
    )


def _view(*snaps: MarketSnapshot) -> LatestSnapshotView:
    v = LatestSnapshotView()
    for s in snaps:
        v.update(s)
    return v


def _strategy(**overrides) -> TriangularArbitrage:
    base = dict(
        exchange=_BINANCE,
        quote=Asset("USDT"),
        intermediate=Asset("BTC"),
        base=Asset("ETH"),
        size_quote=Decimal("100"),
        taker_fee_bps=10,
        min_profit_threshold_usd=Decimal("0.10"),
        valid_for_ms=1000,
        confidence=0.85,
    )
    base.update(overrides)
    return TriangularArbitrage(**base)


# ---- Protocol conformance -------------------------------------------------


def test_satisfies_strategy_protocol():
    assert isinstance(_strategy(), Strategy)


def test_declares_three_symbols_and_one_venue():
    s = _strategy()
    assert s.min_venues == 1
    assert len(s.symbols) == 3
    assert Symbol("BTC", "USDT") in s.symbols
    assert Symbol("ETH", "USDT") in s.symbols
    assert Symbol("ETH", "BTC") in s.symbols


# ---- Missing data ---------------------------------------------------------


def test_returns_none_when_any_pair_missing():
    s = _strategy()
    clk = _FixedClock()
    # Only two of three pairs seeded.
    v = _view(
        _snap("BTC", "USDT", "60000", "60001"),
        _snap("ETH", "USDT", "3000", "3001"),
    )
    assert s.evaluate(v, clk) is None


def test_returns_none_when_no_pairs_seeded():
    assert _strategy().evaluate(LatestSnapshotView(), _FixedClock()) is None


# ---- Below-threshold no-op ------------------------------------------------


def test_returns_none_when_cycle_unprofitable():
    """Pairs at fair triangular parity → fees eat any spread → no
    opportunity."""
    s = _strategy()
    # BTC/USDT = 60000, ETH/USDT = 3000, ETH/BTC = 0.05 → exact parity.
    v = _view(
        _snap("BTC", "USDT", "59999", "60001"),
        _snap("ETH", "USDT", "2999.5", "3000.5"),
        _snap("ETH", "BTC", "0.049995", "0.050005"),
    )
    assert s.evaluate(v, _FixedClock()) is None


# ---- Forward path opportunity --------------------------------------------


def test_forward_path_detected_when_eth_btc_undervalued():
    """If ETH/BTC ask is unusually cheap (e.g. 0.0490 vs parity 0.050),
    forward Q→I→B→Q profits: buying ETH via BTC bridge then selling
    ETH for USDT yields more USDT back."""
    s = _strategy(min_profit_threshold_usd=Decimal("0.01"))
    v = _view(
        _snap("BTC", "USDT", "59999", "60001"),
        _snap("ETH", "USDT", "3050.0", "3050.5"),  # ETH/USDT richer
        _snap("ETH", "BTC", "0.0490", "0.0491"),    # ETH/BTC cheaper
    )
    opp = s.evaluate(v, _FixedClock())
    assert opp is not None
    assert opp.strategy == "triangular"
    assert len(opp.legs) == 3
    # Forward path: BTC/USDT buy → ETH/BTC buy → ETH/USDT sell.
    assert opp.legs[0].symbol == Symbol("BTC", "USDT")
    assert opp.legs[0].side == "buy"
    assert opp.legs[1].symbol == Symbol("ETH", "BTC")
    assert opp.legs[1].side == "buy"
    assert opp.legs[2].symbol == Symbol("ETH", "USDT")
    assert opp.legs[2].side == "sell"
    assert opp.expected_net_profit > 0


def test_forward_legs_share_venue():
    s = _strategy(min_profit_threshold_usd=Decimal("0.01"))
    v = _view(
        _snap("BTC", "USDT", "59999", "60001"),
        _snap("ETH", "USDT", "3050.0", "3050.5"),
        _snap("ETH", "BTC", "0.0490", "0.0491"),
    )
    opp = s.evaluate(v, _FixedClock())
    assert opp is not None
    assert {leg.exchange for leg in opp.legs} == {_BINANCE}


# ---- Reverse path opportunity --------------------------------------------


def test_reverse_path_detected_when_eth_btc_overvalued():
    """If ETH/BTC bid is unusually high (e.g. 0.0510 vs parity 0.050),
    reverse Q→B→I→Q profits: buy ETH directly, swap ETH→BTC at
    favourable bid, sell BTC for USDT."""
    s = _strategy(min_profit_threshold_usd=Decimal("0.01"))
    v = _view(
        _snap("BTC", "USDT", "60000", "60001"),
        _snap("ETH", "USDT", "2999.5", "3000"),  # ETH/USDT cheap to buy
        _snap("ETH", "BTC", "0.0510", "0.0511"),  # ETH/BTC rich bid
    )
    opp = s.evaluate(v, _FixedClock())
    assert opp is not None
    # Reverse path: ETH/USDT buy → ETH/BTC sell → BTC/USDT sell.
    assert opp.legs[0].symbol == Symbol("ETH", "USDT")
    assert opp.legs[0].side == "buy"
    assert opp.legs[1].symbol == Symbol("ETH", "BTC")
    assert opp.legs[1].side == "sell"
    assert opp.legs[2].symbol == Symbol("BTC", "USDT")
    assert opp.legs[2].side == "sell"
    assert opp.expected_net_profit > 0


# ---- Profit math ----------------------------------------------------------


def test_profit_scales_with_size():
    """Doubling size_quote should roughly double profit (fees scale too,
    but linearly with notional)."""
    common = dict(
        quote=Asset("USDT"), intermediate=Asset("BTC"), base=Asset("ETH"),
        taker_fee_bps=10, min_profit_threshold_usd=Decimal("0"),
    )
    s100 = TriangularArbitrage(
        exchange=_BINANCE, size_quote=Decimal("100"), **common,
    )
    s200 = TriangularArbitrage(
        exchange=_BINANCE, size_quote=Decimal("200"), **common,
    )
    v = _view(
        _snap("BTC", "USDT", "59999", "60001"),
        _snap("ETH", "USDT", "3050.0", "3050.5"),
        _snap("ETH", "BTC", "0.0490", "0.0491"),
    )
    p100 = s100.evaluate(v, _FixedClock()).expected_net_profit
    p200 = s200.evaluate(v, _FixedClock()).expected_net_profit
    # Within a small rounding tolerance, doubling notional doubles
    # absolute profit.
    assert abs(p200 / p100 - 2) < Decimal("0.001")


def test_higher_fees_eliminate_marginal_opportunity():
    """A cycle that's barely profitable at 10 bps fees becomes
    unprofitable at 50 bps."""
    common = dict(
        quote=Asset("USDT"), intermediate=Asset("BTC"), base=Asset("ETH"),
        size_quote=Decimal("100"), min_profit_threshold_usd=Decimal("0"),
    )
    cheap = TriangularArbitrage(
        exchange=_BINANCE, taker_fee_bps=10, **common,
    )
    pricey = TriangularArbitrage(
        exchange=_BINANCE, taker_fee_bps=50, **common,
    )
    # Slight forward edge — ~12 bps gross before fees.
    v = _view(
        _snap("BTC", "USDT", "60000", "60001"),
        _snap("ETH", "USDT", "3008", "3008.5"),
        _snap("ETH", "BTC", "0.04996", "0.04997"),
    )
    p_cheap = cheap.evaluate(v, _FixedClock())
    p_pricey = pricey.evaluate(v, _FixedClock())
    assert p_cheap is not None and p_cheap.expected_net_profit > 0
    # At 50 bps the cycle is net-negative → strategy returns None
    # (because threshold = 0 and profit is negative).
    assert p_pricey is None


# ---- Pure-function discipline --------------------------------------------


def test_same_inputs_same_output_modulo_opportunity_id():
    """Strategy is pure — two evaluations of identical inputs produce
    identical legs / profit / strategy. Only `id` (UUID) differs."""
    s = _strategy(min_profit_threshold_usd=Decimal("0.01"))
    v = _view(
        _snap("BTC", "USDT", "59999", "60001"),
        _snap("ETH", "USDT", "3050.0", "3050.5"),
        _snap("ETH", "BTC", "0.0490", "0.0491"),
    )
    clk = _FixedClock()
    a = s.evaluate(v, clk)
    b = s.evaluate(v, clk)
    assert a.strategy == b.strategy == "triangular"
    assert a.legs == b.legs
    assert a.expected_net_profit == b.expected_net_profit
    assert a.id != b.id  # UUIDs differ per call


def test_opportunity_detected_at_uses_injected_clock():
    s = _strategy(min_profit_threshold_usd=Decimal("0.01"))
    v = _view(
        _snap("BTC", "USDT", "59999", "60001"),
        _snap("ETH", "USDT", "3050.0", "3050.5"),
        _snap("ETH", "BTC", "0.0490", "0.0491"),
    )
    clk = _FixedClock(now_ms=1_700_000_123_000)
    opp = s.evaluate(v, clk)
    assert opp is not None
    assert int(opp.detected_at.timestamp() * 1000) == 1_700_000_123_000
