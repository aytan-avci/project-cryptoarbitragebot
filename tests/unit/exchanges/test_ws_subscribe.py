"""WebSocket subscribe — Binance + Bybit, against in-process aiohttp WS server."""

import asyncio
import json
from contextlib import asynccontextmanager

import pytest
from aiohttp import web

from arbitrage_agent.domain import Symbol
from arbitrage_agent.exchanges.binance import BinanceAdapter
from arbitrage_agent.exchanges.bybit import BybitAdapter

BTC = Symbol("BTC", "USDT")


@asynccontextmanager
async def _ws_server(ws_handler, route="/stream"):
    """Start an in-process aiohttp WS server on a random port."""
    app = web.Application()
    app.router.add_get(route, ws_handler)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", 0)
    await site.start()
    port = site._server.sockets[0].getsockname()[1]  # type: ignore[union-attr]
    try:
        yield f"ws://127.0.0.1:{port}"
    finally:
        await runner.cleanup()


# ---- Binance WS -----------------------------------------------------------

@pytest.mark.asyncio
async def test_binance_subscribe_receives_book_ticker():
    """Server emits one combined-stream bookTicker frame; adapter
    parses it and invokes the callback. Task is cancelled by the
    test as soon as the first frame arrives."""

    async def handler(request):
        ws = web.WebSocketResponse()
        await ws.prepare(request)
        await ws.send_json({
            "stream": "btcusdt@bookTicker",
            "data": {
                "u": 12345, "s": "BTCUSDT",
                "b": "60000.00", "B": "1.5",
                "a": "60001.00", "A": "0.8",
            },
        })
        # Keep socket open; the test cancels the task externally.
        await asyncio.sleep(5)
        return ws

    async with _ws_server(handler) as ws_url:
        adapter = BinanceAdapter(ws_base_url=ws_url)
        received = []
        got_frame = asyncio.Event()

        async def cb(snap):
            received.append(snap)
            got_frame.set()

        task = asyncio.create_task(adapter.subscribe([BTC], cb))
        try:
            await asyncio.wait_for(got_frame.wait(), timeout=2.0)
        finally:
            task.cancel()
            try:
                await asyncio.wait_for(task, timeout=1.0)
            except (asyncio.CancelledError, asyncio.TimeoutError, Exception):
                pass
            await adapter.close()

        assert len(received) == 1
        snap = received[0]
        assert snap.exchange == "binance"
        assert str(snap.bid) == "60000.00"
        assert str(snap.ask) == "60001.00"


@pytest.mark.asyncio
async def test_binance_parser_skips_malformed_frame():
    adapter = BinanceAdapter()
    result = adapter._parse_book_ticker_frame(
        '{"this": "is not a bookTicker"}',
        {"BTCUSDT": BTC},
    )
    assert result is None


@pytest.mark.asyncio
async def test_binance_parser_handles_raw_frame_without_stream_wrapper():
    """Some single-stream URLs return frames without the `stream` wrapper."""
    adapter = BinanceAdapter()
    raw = json.dumps({
        "u": 1, "s": "BTCUSDT",
        "b": "60000", "B": "1",
        "a": "60001", "A": "1",
    })
    snap = adapter._parse_book_ticker_frame(raw, {"BTCUSDT": BTC})
    assert snap is not None
    assert snap.symbol == BTC


# ---- Bybit WS -------------------------------------------------------------

@pytest.mark.asyncio
async def test_bybit_subscribe_receives_orderbook_frame():

    async def handler(request):
        ws = web.WebSocketResponse()
        await ws.prepare(request)
        # Expect subscription request
        sub_msg = await ws.receive_json()
        assert sub_msg["op"] == "subscribe"
        assert "orderbook.1.BTCUSDT" in sub_msg["args"]
        # Send ack (should be skipped by parser)
        await ws.send_json({"op": "subscribe", "success": True})
        # Send a data frame
        await ws.send_json({
            "topic": "orderbook.1.BTCUSDT",
            "type": "snapshot",
            "data": {
                "s": "BTCUSDT",
                "b": [["60100.00", "0.95"], ["60099.50", "0.40"]],
                "a": [["60101.00", "0.60"], ["60102.00", "0.30"]],
                "u": 100, "seq": 1,
            },
            "cts": 1234567890,
            "ts": 1234567891,
        })
        await asyncio.sleep(0.1)
        await ws.close()
        return ws

    async with _ws_server(handler, route="/") as ws_url:
        adapter = BybitAdapter(ws_base_url=ws_url)
        received = []
        got_frame = asyncio.Event()

        async def cb(snap):
            received.append(snap)
            got_frame.set()

        task = asyncio.create_task(adapter.subscribe([BTC], cb))
        try:
            await asyncio.wait_for(got_frame.wait(), timeout=2.0)
        finally:
            task.cancel()
            try:
                await asyncio.wait_for(task, timeout=1.0)
            except (asyncio.CancelledError, asyncio.TimeoutError, Exception):
                pass
            await adapter.close()

        assert len(received) >= 1
        snap = received[0]
        assert snap.exchange == "bybit"
        assert str(snap.bid) == "60100.00"
        assert str(snap.ask) == "60101.00"


@pytest.mark.asyncio
async def test_bybit_parser_skips_ack():
    adapter = BybitAdapter()
    result = adapter._parse_orderbook_frame(
        '{"op": "subscribe", "success": true}',
        {"BTCUSDT": BTC},
    )
    assert result is None


@pytest.mark.asyncio
async def test_bybit_parser_skips_unknown_symbol():
    adapter = BybitAdapter()
    raw = json.dumps({
        "topic": "orderbook.1.ETHUSDT",
        "data": {
            "s": "ETHUSDT",
            "b": [["3000", "1"]],
            "a": [["3001", "1"]],
        },
    })
    result = adapter._parse_orderbook_frame(raw, {"BTCUSDT": BTC})
    assert result is None  # only BTC subscribed; ETH frame ignored
