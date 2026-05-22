"""BinanceAdapter tests — uses aiohttp's in-process test server.

No network access. Every test spins up a tiny aiohttp app that returns the
canned response we'd expect from Binance.
"""

from contextlib import asynccontextmanager
from decimal import Decimal

import pytest
from aiohttp import web

from arbitrage_agent.domain import Symbol
from arbitrage_agent.exchanges.base import ExchangeAdapter
from arbitrage_agent.exchanges.binance import BinanceAdapter
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
    """Start an in-process aiohttp app on a random port; yield its base URL."""
    app = web.Application()
    app.router.add_get("/api/v3/depth", handler)
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
        adapter = BinanceAdapter()
        assert isinstance(adapter, ExchangeAdapter)

    def test_id_returns_binance(self):
        assert BinanceAdapter().id == "binance"


class TestSymbolMapping:
    def test_to_native(self):
        assert BinanceAdapter._to_native(Symbol("BTC", "USDT")) == "BTCUSDT"
        assert BinanceAdapter._to_native(Symbol("ETH", "USD")) == "ETHUSD"


# ---- fetch_book_snapshot ---------------------------------------------------

@pytest.mark.asyncio
async def test_happy_path_parses_top_of_book():
    async def handler(request):
        assert request.query["symbol"] == "BTCUSDT"
        return web.json_response({
            "lastUpdateId": 1027024,
            "bids": [["60000.00", "1.500"], ["59999.99", "0.500"]],
            "asks": [["60001.00", "0.800"], ["60002.00", "0.200"]],
        })

    async with _stub_server(handler) as base_url:
        adapter = BinanceAdapter(base_url=base_url)
        snap = await adapter.fetch_book_snapshot(BTC)
        assert snap.exchange == "binance"
        assert snap.symbol == BTC
        assert snap.bid == Decimal("60000.00")
        assert snap.ask == Decimal("60001.00")
        assert snap.bid_size == Decimal("1.500")
        assert snap.ask_size == Decimal("0.800")
        assert snap.timestamp_utc.tzinfo is not None
        await adapter.close()


@pytest.mark.asyncio
async def test_429_raises_rate_limited():
    async def handler(request):
        return web.Response(status=429, text="rate limited")

    async with _stub_server(handler) as base_url:
        adapter = BinanceAdapter(base_url=base_url)
        with pytest.raises(RateLimited):
            await adapter.fetch_book_snapshot(BTC)
        await adapter.close()


@pytest.mark.asyncio
async def test_418_raises_permanent_failure():
    async def handler(request):
        return web.Response(status=418, text="ip banned")

    async with _stub_server(handler) as base_url:
        adapter = BinanceAdapter(base_url=base_url)
        with pytest.raises(PermanentFailure):
            await adapter.fetch_book_snapshot(BTC)
        await adapter.close()


@pytest.mark.asyncio
async def test_400_raises_invalid_order():
    async def handler(request):
        return web.Response(
            status=400, text='{"code":-1121,"msg":"Invalid symbol."}'
        )

    async with _stub_server(handler) as base_url:
        adapter = BinanceAdapter(base_url=base_url)
        with pytest.raises(InvalidOrder):
            await adapter.fetch_book_snapshot(BTC)
        await adapter.close()


@pytest.mark.asyncio
async def test_500_raises_temporary_failure():
    async def handler(request):
        return web.Response(status=503, text="overloaded")

    async with _stub_server(handler) as base_url:
        adapter = BinanceAdapter(base_url=base_url)
        with pytest.raises(TemporaryFailure):
            await adapter.fetch_book_snapshot(BTC)
        await adapter.close()


@pytest.mark.asyncio
async def test_empty_book_raises_market_halted():
    async def handler(request):
        return web.json_response({"bids": [], "asks": []})

    async with _stub_server(handler) as base_url:
        adapter = BinanceAdapter(base_url=base_url)
        with pytest.raises(MarketHalted):
            await adapter.fetch_book_snapshot(BTC)
        await adapter.close()


@pytest.mark.asyncio
async def test_malformed_response_raises_permanent_failure():
    async def handler(request):
        return web.json_response({"unexpected": "shape"})

    async with _stub_server(handler) as base_url:
        adapter = BinanceAdapter(base_url=base_url)
        with pytest.raises(PermanentFailure):
            await adapter.fetch_book_snapshot(BTC)
        await adapter.close()


# Faz 7b implemented place_order / cancel_order / fetch_balance / fetch_fills
# against the signed REST endpoints. Comprehensive auth + signing + S5
# coverage in test_binance_auth.py. Live-mode S3 decorator coverage in
# test_live_mode_decorator.py.


# subscribe() is now implemented (Faz 7c) — comprehensive tests in
# test_ws_subscribe.py against an in-process aiohttp WS server. The
# obsolete NotImplementedError sentinel is intentionally removed here
# (would hang trying to dial the real Binance WS).
