"""PaperExchange — Faz 5a tests.

Scope: structural conformance to `ExchangeAdapter`, working
`fetch_book_snapshot` (timestamp refresh, missing-symbol behaviour), and
`place_order` accepting only approved decisions. Other 4 methods are
expected to raise `NotImplementedError` (Faz 5b+ sentinel).
"""

import asyncio
import uuid
from decimal import Decimal

import pytest

from arbitrage_agent.domain import (
    Asset,
    ExchangeId,
    MarketSnapshot,
    OrderId,
    OrderIntent,
    RiskDecision,
    Symbol,
    new_opportunity_id,
    now_utc,
    price,
    volume,
)
from arbitrage_agent.exchanges.base import ExchangeAdapter
from arbitrage_agent.exchanges.paper import PaperExchange


# ---- Fixtures --------------------------------------------------------------

def _btc_snapshot() -> MarketSnapshot:
    return MarketSnapshot(
        exchange=ExchangeId("paper"),
        symbol=Symbol("BTC", "USDT"),
        bid=price("60000.00"),
        ask=price("60001.00"),
        bid_size=volume("1.0"),
        ask_size=volume("0.8"),
        timestamp_utc=now_utc(),
    )


def _approved(opportunity_id=None) -> RiskDecision:
    return RiskDecision(
        opportunity_id=opportunity_id or new_opportunity_id(),
        approved=True,
        reason="all checks passed",
    )


def _rejected() -> RiskDecision:
    return RiskDecision(
        opportunity_id=new_opportunity_id(),
        approved=False,
        reason="position_limit_exceeded",
    )


def _intent_buy() -> OrderIntent:
    return OrderIntent(
        exchange=ExchangeId("paper"),
        symbol=Symbol("BTC", "USDT"),
        side="buy",
        quantity=volume("0.01"),
        limit_price=price("60000.00"),
    )


# ---- Protocol conformance --------------------------------------------------

class TestProtocolConformance:
    def test_paper_is_exchange_adapter(self):
        ex = PaperExchange()
        assert isinstance(ex, ExchangeAdapter)

    def test_id_property_returns_exchange_id(self):
        ex = PaperExchange(name="paper")
        assert ex.id == ExchangeId("paper")

    def test_custom_name_propagates_to_id(self):
        ex = PaperExchange(name="paper-eu")
        assert ex.id == ExchangeId("paper-eu")


# ---- fetch_book_snapshot ---------------------------------------------------

class TestFetchBookSnapshot:
    def test_returns_seeded_snapshot(self):
        snap = _btc_snapshot()
        ex = PaperExchange(prices={snap.symbol: snap})
        out = asyncio.run(ex.fetch_book_snapshot(Symbol("BTC", "USDT")))
        assert out.exchange == snap.exchange
        assert out.symbol == snap.symbol
        assert out.bid == snap.bid
        assert out.ask == snap.ask
        assert out.bid_size == snap.bid_size
        assert out.ask_size == snap.ask_size

    def test_refreshes_timestamp_on_each_fetch(self):
        snap = _btc_snapshot()
        ex = PaperExchange(prices={snap.symbol: snap})
        out1 = asyncio.run(ex.fetch_book_snapshot(Symbol("BTC", "USDT")))
        out2 = asyncio.run(ex.fetch_book_snapshot(Symbol("BTC", "USDT")))
        assert out1.timestamp_utc <= out2.timestamp_utc
        # New value differs from cached source (real clock has progressed
        # OR at minimum the field was rebuilt, not aliased).
        assert out1.timestamp_utc != snap.timestamp_utc or out2.timestamp_utc != snap.timestamp_utc

    def test_missing_symbol_raises_keyerror(self):
        ex = PaperExchange()
        with pytest.raises(KeyError):
            asyncio.run(ex.fetch_book_snapshot(Symbol("ETH", "USDT")))

    def test_set_price_replaces_entry(self):
        ex = PaperExchange()
        ex.set_price(_btc_snapshot())
        out = asyncio.run(ex.fetch_book_snapshot(Symbol("BTC", "USDT")))
        assert out.bid == Decimal("60000.00")


# ---- place_order -----------------------------------------------------------

class TestPlaceOrder:
    def test_approved_returns_unique_order_id(self):
        ex = PaperExchange()
        a = asyncio.run(ex.place_order(_intent_buy(), _approved()))
        b = asyncio.run(ex.place_order(_intent_buy(), _approved()))
        assert a != b
        uuid.UUID(a)  # OrderId is a UUID4 string
        uuid.UUID(b)

    def test_rejected_decision_raises_valueerror(self):
        ex = PaperExchange()
        with pytest.raises(ValueError, match="approved decision"):
            asyncio.run(ex.place_order(_intent_buy(), _rejected()))

    def test_return_value_is_order_id_typed(self):
        ex = PaperExchange()
        oid = asyncio.run(ex.place_order(_intent_buy(), _approved()))
        # NewType erases at runtime; this is a string round-trip check
        assert isinstance(oid, str)


# ---- Faz 6: fetch_fills + place_order emits Fill --------------------------

class TestFillRecording:
    def test_place_order_records_fill_at_limit_price(self):
        ex = PaperExchange()
        intent = _intent_buy()
        opp_id = new_opportunity_id()
        decision = _approved(opp_id)
        asyncio.run(ex.place_order(intent, decision))
        fills = asyncio.run(ex.fetch_fills(since=now_utc().replace(year=2020)))
        assert len(fills) == 1
        f = fills[0]
        assert f.opportunity_id == opp_id
        assert f.price == intent.limit_price
        assert f.volume == intent.quantity
        assert f.side == "buy"
        assert f.symbol == intent.symbol
        assert f.exchange == ex.id

    def test_fee_computed_at_taker_rate(self):
        """fee = limit_price × quantity × (taker_fee_bps / 10_000).
        intent_buy = 0.01 BTC × 60_000 USD × 0.001 (10 bps) = 0.60 USD."""
        from decimal import Decimal
        ex = PaperExchange(taker_fee_bps=10)
        asyncio.run(ex.place_order(_intent_buy(), _approved()))
        fills = asyncio.run(ex.fetch_fills(since=now_utc().replace(year=2020)))
        assert fills[0].fee == Decimal("0.6")

    def test_fetch_fills_filters_by_since(self):
        ex = PaperExchange()
        asyncio.run(ex.place_order(_intent_buy(), _approved()))
        from datetime import timedelta
        future = now_utc() + timedelta(seconds=10)
        assert asyncio.run(ex.fetch_fills(since=future)) == []

    def test_fetch_fills_empty_initially(self):
        ex = PaperExchange()
        assert asyncio.run(ex.fetch_fills(since=now_utc())) == []

    def test_rejected_order_emits_no_fill(self):
        ex = PaperExchange()
        with pytest.raises(ValueError):
            asyncio.run(ex.place_order(_intent_buy(), _rejected()))
        assert asyncio.run(ex.fetch_fills(since=now_utc().replace(year=2020))) == []


# ---- Sentinel: still-unimplemented (Faz 7+) -------------------------------

class TestUnimplementedFaz7Methods:
    def test_subscribe_not_implemented(self):
        ex = PaperExchange()
        async def cb(snap): pass
        with pytest.raises(NotImplementedError):
            asyncio.run(ex.subscribe([Symbol("BTC", "USDT")], cb))

    def test_cancel_order_is_noop(self):
        """Faz 7g-c: PaperExchange.cancel_order accepts the call so the
        hedger's best-effort cancel loop can traverse mixed paper/live
        adapter sets without special-casing. Returns None silently."""
        ex = PaperExchange()
        assert asyncio.run(ex.cancel_order(OrderId("dummy"))) is None

    def test_fetch_balance_not_implemented(self):
        ex = PaperExchange()
        with pytest.raises(NotImplementedError):
            asyncio.run(ex.fetch_balance(Asset("USDT")))
