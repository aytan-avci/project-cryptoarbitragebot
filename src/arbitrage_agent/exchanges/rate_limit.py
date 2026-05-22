"""Token-bucket rate limiter — per exchange.

Each adapter owns one of these. `await bucket.acquire()` before every API
call. If tokens are exhausted, the call sleeps until enough have refilled.

Per `skills/exchange-integration/SKILL.md § Rate Limits`: one bucket per
exchange, sized to the documented limit minus a margin (default 20%).
"""

import asyncio
import time


class TokenBucket:
    """Async token bucket. Concurrency-safe via a single asyncio.Lock."""

    def __init__(self, rate_per_minute: int, capacity: int | None = None) -> None:
        if rate_per_minute <= 0:
            raise ValueError("rate_per_minute must be positive")
        self._rate_per_sec = rate_per_minute / 60.0
        self._capacity = float(capacity if capacity is not None else rate_per_minute)
        self._tokens = self._capacity
        self._last = time.monotonic()
        self._lock = asyncio.Lock()

    async def acquire(self, cost: float = 1.0) -> None:
        """Consume `cost` tokens. Sleep until enough are available."""
        if cost > self._capacity:
            raise ValueError(
                f"cost {cost} exceeds bucket capacity {self._capacity}"
            )
        while True:
            async with self._lock:
                now = time.monotonic()
                elapsed = now - self._last
                self._tokens = min(
                    self._capacity, self._tokens + elapsed * self._rate_per_sec
                )
                self._last = now
                if self._tokens >= cost:
                    self._tokens -= cost
                    return
                wait = (cost - self._tokens) / self._rate_per_sec
            await asyncio.sleep(wait)

    @property
    def available(self) -> float:
        """Current token count (lock-free; for instrumentation only)."""
        now = time.monotonic()
        elapsed = now - self._last
        return min(self._capacity, self._tokens + elapsed * self._rate_per_sec)
