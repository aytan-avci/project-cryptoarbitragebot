"""TokenBucket — async token bucket rate limiter."""

import asyncio
import time

import pytest

from arbitrage_agent.exchanges.rate_limit import TokenBucket


@pytest.mark.asyncio
async def test_full_bucket_acquires_immediately():
    bucket = TokenBucket(rate_per_minute=60)  # 1 token/sec, capacity 60
    start = time.monotonic()
    await bucket.acquire()
    elapsed = time.monotonic() - start
    assert elapsed < 0.05  # essentially immediate


@pytest.mark.asyncio
async def test_drains_then_waits():
    bucket = TokenBucket(rate_per_minute=600)  # 10/sec
    # Drain the whole bucket immediately
    for _ in range(int(bucket.available)):
        await bucket.acquire()
    # Next acquire should wait ~0.1s for one token to refill
    start = time.monotonic()
    await bucket.acquire()
    elapsed = time.monotonic() - start
    assert 0.05 < elapsed < 0.4


@pytest.mark.asyncio
async def test_rejects_cost_above_capacity():
    bucket = TokenBucket(rate_per_minute=60, capacity=10)
    with pytest.raises(ValueError):
        await bucket.acquire(cost=11)


def test_rejects_nonpositive_rate():
    with pytest.raises(ValueError):
        TokenBucket(rate_per_minute=0)
    with pytest.raises(ValueError):
        TokenBucket(rate_per_minute=-5)


@pytest.mark.asyncio
async def test_concurrent_acquires_serialize():
    bucket = TokenBucket(rate_per_minute=600)
    # Two concurrent acquires when bucket has ≥2 tokens both succeed fast
    start = time.monotonic()
    await asyncio.gather(bucket.acquire(), bucket.acquire())
    assert time.monotonic() - start < 0.1
