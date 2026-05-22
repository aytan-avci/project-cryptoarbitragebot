"""In-memory snapshot store + async pub-sub bus.

`LatestSnapshotView` keeps the most recent `MarketSnapshot` per
`(exchange, symbol)` pair — `MarketView` Protocol implementation.

`MarketDataBus` is the Faz 7c addition: an async pub-sub fan-out that
adapter `subscribe` callbacks publish to, and the orchestration
pipeline consumes from.
"""

import asyncio
from typing import Awaitable, Callable

from arbitrage_agent.domain import ExchangeId, MarketSnapshot, Symbol

SnapshotHandler = Callable[[MarketSnapshot], Awaitable[None]]


class LatestSnapshotView:
    """Concrete `MarketView` — latest-only, in-memory."""

    def __init__(self) -> None:
        self._latest: dict[tuple[ExchangeId, Symbol], MarketSnapshot] = {}

    def update(self, snapshot: MarketSnapshot) -> None:
        """Replace the entry for `(snapshot.exchange, snapshot.symbol)`."""
        self._latest[(snapshot.exchange, snapshot.symbol)] = snapshot

    def snapshot(
        self, exchange: ExchangeId, symbol: Symbol
    ) -> MarketSnapshot | None:
        """Latest known snapshot, or `None` if never seen."""
        return self._latest.get((exchange, symbol))


class MarketDataBus:
    """Async pub-sub for `MarketSnapshot`. Subscribers are coroutines
    invoked sequentially per publish (the natural serialization makes
    strategy / risk / execution coherent without an explicit lock —
    `subscribe` handlers should be fast and non-blocking aside from
    awaiting downstream consumers)."""

    def __init__(self) -> None:
        self._subscribers: list[SnapshotHandler] = []

    def subscribe(self, handler: SnapshotHandler) -> None:
        """Register an async callback for every published snapshot."""
        self._subscribers.append(handler)

    async def publish(self, snapshot: MarketSnapshot) -> None:
        """Fan out to every subscriber in registration order. A handler
        raising an exception is logged but does NOT block other handlers
        (best-effort delivery)."""
        for handler in self._subscribers:
            try:
                await handler(snapshot)
            except Exception:  # noqa: BLE001 — best-effort fan-out
                # Real production would emit a structured error event
                # here; for Faz 7c we accept the trade-off of swallowing
                # and continuing (otherwise one bad subscriber kills
                # data flow for everyone).
                pass

    @property
    def subscriber_count(self) -> int:
        return len(self._subscribers)
