"""BybitAdapter tests — uses aiohttp's in-process test server.

No network access. Bybit's quirk: HTTP 200 even on app errors —
discriminator is the `retCode` field in the JSON body.
"""

from contextlib import asynccontextmanager
from decimal import Decimal

import pytest
from aiohttp import web

from arbitrage_agent.domain import Symbol
from arbitrage_agent.exchanges.base import ExchangeAdapter
from arbitrage_agent.exchanges.bybit import BybitAdapter
from arbitrage_agent.exchanges.errors import (
    InvalidOrder,
    MarketHalted,
    PermanentFailure,
    RateLimited,
    TemporaryFailure,
)

BTC = Symbol("BTC", "USDT")


@asynccontextmanager
async def _stub_server(handler):
    app = web.Application()
    app.router.add_get("/v5/market/orderbook", handler)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", 0)
    await site.start()
    port = site._server.sockets[0].getsockname()[1]  # type: ignore[union-attr]
    try:
        yield f"http://127.0.0.1:{port}"
    finally:
        await runner.cleanup()


# ---- Protocol conformance --------------------------------------------------


class TestProtocolConformance:
    def test_is_exchange_adapter(self):
        assert isinstance(BybitAdapter(), ExchangeAdapter)

    def test_id_returns_bybit(self):
        assert BybitAdapter().id == "bybit"


class TestSymbolMapping:
    def test_to_native(self):
        assert BybitAdapter._to_native(Symbol("BTC", "USDT")) == "BTCUSDT"
        assert BybitAdapter._to_native(Symbol("ETH", "USDT")) == "ETHUSDT"


# ---- fetch_book_snapshot ---------------------------------------------------


@pytest.mark.asyncio
async def test_happy_path_parses_top_of_book():
    async def handler(request):
        assert request.query["symbol"] == "BTCUSDT"
        assert request.query["category"] == "spot"
        return web.json_response({
            "retCode": 0,
            "retMsg": "OK",
            "result": {
                "s": "BTCUSDT",
                "b": [["60100.00", "0.95"], ["60099.50", "0.40"]],
                "a": [["60101.00", "0.60"], ["60102.00", "0.30"]],
                "ts": 1234567890,
                "u": 12345,
            },
            "time": 1234567890,
        })

    async with _stub_server(handler) as base_url:
        adapter = BybitAdapter(base_url=base_url)
        snap = await adapter.fetch_book_snapshot(BTC)
        assert snap.exchange == "bybit"
        assert snap.symbol == BTC
        assert snap.bid == Decimal("60100.00")
        assert snap.ask == Decimal("60101.00")
        assert snap.bid_size == Decimal("0.95")
        assert snap.ask_size == Decimal("0.60")
        assert snap.timestamp_utc.tzinfo is not None
        await adapter.close()


@pytest.mark.asyncio
async def test_retcode_10006_raises_rate_limited():
    async def handler(request):
        return web.json_response({"retCode": 10006, "retMsg": "rate limit"})

    async with _stub_server(handler) as base_url:
        adapter = BybitAdapter(base_url=base_url)
        with pytest.raises(RateLimited):
            await adapter.fetch_book_snapshot(BTC)
        await adapter.close()


@pytest.mark.asyncio
async def test_retcode_10001_raises_invalid_order():
    async def handler(request):
        return web.json_response({"retCode": 10001, "retMsg": "invalid symbol"})

    async with _stub_server(handler) as base_url:
        adapter = BybitAdapter(base_url=base_url)
        with pytest.raises(InvalidOrder):
            await adapter.fetch_book_snapshot(BTC)
        await adapter.close()


@pytest.mark.asyncio
async def test_retcode_10005_raises_permanent_failure():
    async def handler(request):
        return web.json_response({"retCode": 10005, "retMsg": "permission denied"})

    async with _stub_server(handler) as base_url:
        adapter = BybitAdapter(base_url=base_url)
        with pytest.raises(PermanentFailure):
            await adapter.fetch_book_snapshot(BTC)
        await adapter.close()


@pytest.mark.asyncio
async def test_unknown_retcode_raises_temporary_failure():
    async def handler(request):
        return web.json_response({"retCode": 99999, "retMsg": "future code"})

    async with _stub_server(handler) as base_url:
        adapter = BybitAdapter(base_url=base_url)
        with pytest.raises(TemporaryFailure):
            await adapter.fetch_book_snapshot(BTC)
        await adapter.close()


@pytest.mark.asyncio
async def test_http_500_raises_temporary_failure():
    async def handler(request):
        return web.Response(status=503, text="upstream")

    async with _stub_server(handler) as base_url:
        adapter = BybitAdapter(base_url=base_url)
        with pytest.raises(TemporaryFailure):
            await adapter.fetch_book_snapshot(BTC)
        await adapter.close()


@pytest.mark.asyncio
async def test_http_429_raises_rate_limited():
    async def handler(request):
        return web.Response(status=429, text="rate limited")

    async with _stub_server(handler) as base_url:
        adapter = BybitAdapter(base_url=base_url)
        with pytest.raises(RateLimited):
            await adapter.fetch_book_snapshot(BTC)
        await adapter.close()


@pytest.mark.asyncio
async def test_empty_book_raises_market_halted():
    async def handler(request):
        return web.json_response({
            "retCode": 0,
            "result": {"b": [], "a": []},
        })

    async with _stub_server(handler) as base_url:
        adapter = BybitAdapter(base_url=base_url)
        with pytest.raises(MarketHalted):
            await adapter.fetch_book_snapshot(BTC)
        await adapter.close()


@pytest.mark.asyncio
async def test_malformed_response_raises_permanent_failure():
    async def handler(request):
        return web.json_response({"retCode": 0, "result": {"no_bids_here": True}})

    async with _stub_server(handler) as base_url:
        adapter = BybitAdapter(base_url=base_url)
        with pytest.raises(PermanentFailure):
            await adapter.fetch_book_snapshot(BTC)
        await adapter.close()


# ---- Faz 7b sentinel methods (S3 guards them) -----------------------------


@pytest.mark.asyncio
async def test_place_order_blocked_in_paper_mode(monkeypatch):
    monkeypatch.setenv("EXECUTION_MODE", "paper")
    from arbitrage_agent.domain import (
        ExchangeId, OrderIntent, RiskDecision,
        new_opportunity_id, price, volume,
    )
    adapter = BybitAdapter()
    intent = OrderIntent(
        exchange=ExchangeId("bybit"), symbol=BTC, side="buy",
        quantity=volume("0.001"), limit_price=price("60000"),
    )
    decision = RiskDecision(
        opportunity_id=new_opportunity_id(), approved=True, reason="ok",
    )
    with pytest.raises(PermissionError):
        await adapter.place_order(intent, decision)


# subscribe() is now implemented (Faz 7c) — see test_ws_subscribe.py
# for Bybit WS coverage. Sentinel removed (would hang on real WS dial).
