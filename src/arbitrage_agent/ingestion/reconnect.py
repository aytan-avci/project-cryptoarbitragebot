"""Exponential backoff helper for WebSocket reconnect loops.

Per `skills/market-data-ingestion/SKILL.md`. Used by every adapter's
`subscribe` to space out reconnect attempts after a disconnect.
"""

import random


class ExponentialBackoff:
    """Stateful backoff calculator. Call `next()` to get the next delay
    in seconds; call `reset()` after a successful (re)connection."""

    def __init__(
        self,
        initial_s: float = 1.0,
        factor: float = 2.0,
        max_s: float = 30.0,
        jitter_ratio: float = 0.1,
    ) -> None:
        if initial_s <= 0 or max_s <= 0 or factor <= 1.0:
            raise ValueError("initial_s/max_s positive; factor > 1.0")
        self._initial = initial_s
        self._factor = factor
        self._max = max_s
        self._jitter = jitter_ratio
        self._attempt = 0

    def next(self) -> float:
        """Return the next delay in seconds and advance the attempt counter."""
        delay = min(self._initial * (self._factor ** self._attempt), self._max)
        self._attempt += 1
        if self._jitter > 0:
            spread = delay * self._jitter
            delay += random.uniform(-spread, spread)
        return max(0.1, delay)

    def reset(self) -> None:
        """Call after a successful connection. Next `.next()` starts at initial."""
        self._attempt = 0

    @property
    def attempt(self) -> int:
        return self._attempt
