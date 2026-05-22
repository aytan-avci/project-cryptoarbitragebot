"""MarketDataBus — async pub-sub fan-out."""

import pytest

from arbitrage_agent.domain import (
    ExchangeId,
    MarketSnapshot,
    Symbol,
    now_utc,
    price,
    volume,
)
from arbitrage_agent.ingestion.bus import MarketDataBus


def _snap() -> MarketSnapshot:
    return MarketSnapshot(
        exchange=ExchangeId("paper"), symbol=Symbol("BTC", "USDT"),
        bid=price("60000"), ask=price("60001"),
        bid_size=volume("1"), ask_size=volume("1"),
        timestamp_utc=now_utc(),
    )


@pytest.mark.asyncio
async def test_no_subscribers_publish_noop():
    bus = MarketDataBus()
    await bus.publish(_snap())  # no exception


@pytest.mark.asyncio
async def test_single_subscriber_receives():
    bus = MarketDataBus()
    received = []
    async def handler(s): received.append(s)
    bus.subscribe(handler)
    snap = _snap()
    await bus.publish(snap)
    assert received == [snap]


@pytest.mark.asyncio
async def test_multiple_subscribers_fan_out():
    bus = MarketDataBus()
    a, b = [], []
    async def ha(s): a.append(s)
    async def hb(s): b.append(s)
    bus.subscribe(ha); bus.subscribe(hb)
    snap = _snap()
    await bus.publish(snap)
    assert a == [snap]
    assert b == [snap]


@pytest.mark.asyncio
async def test_failing_subscriber_does_not_block_others():
    bus = MarketDataBus()
    received = []
    async def bad(_): raise RuntimeError("boom")
    async def good(s): received.append(s)
    bus.subscribe(bad); bus.subscribe(good)
    snap = _snap()
    await bus.publish(snap)  # no exception escapes
    assert received == [snap]


@pytest.mark.asyncio
async def test_subscriber_count():
    bus = MarketDataBus()
    assert bus.subscriber_count == 0
    async def h(_): pass
    bus.subscribe(h); bus.subscribe(h)
    assert bus.subscriber_count == 2
