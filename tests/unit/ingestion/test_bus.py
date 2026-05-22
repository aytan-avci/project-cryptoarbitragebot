"""LatestSnapshotView — in-memory MarketView."""

from arbitrage_agent.domain import (
    ExchangeId,
    MarketSnapshot,
    Symbol,
    now_utc,
    price,
    volume,
)
from arbitrage_agent.ingestion.bus import LatestSnapshotView
from arbitrage_agent.strategies.base import MarketView


def _snap(
    exchange: str = "binance",
    base: str = "BTC",
    quote: str = "USDT",
    bid: str = "60000",
) -> MarketSnapshot:
    return MarketSnapshot(
        exchange=ExchangeId(exchange),
        symbol=Symbol(base, quote),
        bid=price(bid),
        ask=price(str(int(bid) + 1)),
        bid_size=volume("1"),
        ask_size=volume("1"),
        timestamp_utc=now_utc(),
    )


def test_satisfies_market_view_protocol():
    assert isinstance(LatestSnapshotView(), MarketView)


def test_empty_view_returns_none():
    v = LatestSnapshotView()
    assert v.snapshot(ExchangeId("binance"), Symbol("BTC", "USDT")) is None


def test_update_then_snapshot():
    v = LatestSnapshotView()
    s = _snap()
    v.update(s)
    out = v.snapshot(ExchangeId("binance"), Symbol("BTC", "USDT"))
    assert out is not None
    assert out.bid == s.bid


def test_update_replaces_previous():
    v = LatestSnapshotView()
    v.update(_snap(bid="60000"))
    v.update(_snap(bid="60100"))
    out = v.snapshot(ExchangeId("binance"), Symbol("BTC", "USDT"))
    assert out is not None
    assert str(out.bid) == "60100"


def test_independent_keys():
    v = LatestSnapshotView()
    v.update(_snap(exchange="binance", bid="60000"))
    v.update(_snap(exchange="bybit", bid="60050"))
    a = v.snapshot(ExchangeId("binance"), Symbol("BTC", "USDT"))
    b = v.snapshot(ExchangeId("bybit"), Symbol("BTC", "USDT"))
    assert a is not None and b is not None
    assert a.bid != b.bid


def test_independent_symbols():
    v = LatestSnapshotView()
    v.update(_snap(base="BTC"))
    v.update(_snap(base="ETH", bid="3000"))
    assert v.snapshot(ExchangeId("binance"), Symbol("BTC", "USDT")) is not None
    assert v.snapshot(ExchangeId("binance"), Symbol("ETH", "USDT")) is not None
