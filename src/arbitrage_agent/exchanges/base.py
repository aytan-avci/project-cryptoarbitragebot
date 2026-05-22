"""`ExchangeAdapter` Protocol — the contract every venue adapter satisfies.

Definitive source: `skills/exchange-integration/SKILL.md § The Protocol`.
ARCHITECTURE.md § 6 sketches it; SKILL.md is normative.

The boundary rule (`PROJECT_STRUCTURE.md § Rules`): ccxt / native objects
MUST NOT cross this protocol — only domain types in, domain types out.

This module also exports `requires_live_mode`, the SECURITY.md S3
defence-in-depth decorator. Every LIVE adapter applies it to
authenticated methods (`place_order`, `cancel_order`, `fetch_balance`,
`fetch_fills`). PaperExchange does NOT — paper is the safe-default
testing surface and must work under any `EXECUTION_MODE`.
"""

import os
from datetime import datetime
from functools import wraps
from typing import Any, Awaitable, Callable, Protocol, TypeVar, runtime_checkable

from arbitrage_agent.domain import (
    Asset,
    ExchangeId,
    Fill,
    MarketSnapshot,
    OrderId,
    OrderIntent,
    RiskDecision,
    Symbol,
    Volume,
)

SnapshotCallback = Callable[[MarketSnapshot], Awaitable[None]]
"""Coroutine that ingestion uses to consume snapshots from a subscription."""


@runtime_checkable
class ExchangeAdapter(Protocol):
    """Structural typing — any class with these members satisfies it."""

    @property
    def id(self) -> ExchangeId:
        """The exchange identifier (e.g., `ExchangeId('binance')`)."""
        ...

    async def subscribe(
        self, symbols: list[Symbol], on_snapshot: SnapshotCallback
    ) -> None:
        """Open WS subscription; invoke `on_snapshot` for every tick.

        Long-running coroutine; returns only on shutdown / fatal error.
        """
        ...

    async def fetch_book_snapshot(self, symbol: Symbol) -> MarketSnapshot:
        """Top-of-book snapshot via REST. Used for gap recovery."""
        ...

    async def place_order(
        self, intent: OrderIntent, decision: RiskDecision
    ) -> OrderId:
        """Place a single leg.

        `decision.approved` MUST be True; any other input MUST raise
        (CLAUDE.md § 2 C2 — gate enforced at the adapter as well).
        """
        ...

    async def cancel_order(self, order_id: OrderId) -> None:
        """Cancel a previously placed order. Idempotent: cancelling an
        already-terminal order returns without raising."""
        ...

    async def fetch_balance(self, asset: Asset) -> Volume:
        """Current free balance of `asset` on this exchange."""
        ...

    async def fetch_fills(self, since: datetime) -> list[Fill]:
        """Fills observed at or after `since` (tz-aware UTC)."""
        ...


# ---- SECURITY.md S3 — live-mode programmatic guard --------------------

_T = TypeVar("_T")


def requires_live_mode(
    method: Callable[..., Awaitable[_T]],
) -> Callable[..., Awaitable[_T]]:
    """Decorator. Raises ``PermissionError`` if `EXECUTION_MODE != 'live'`.

    Apply to authenticated adapter methods (`place_order`, `cancel_order`,
    `fetch_balance`, `fetch_fills`) on any LIVE adapter (Binance, Bybit,
    …). PaperExchange does not use this decorator — paper trading is
    safe under any execution mode by construction.

    Defence-in-depth for CLAUDE.md C3 + SECURITY.md S3. Reads `EXECUTION_
    MODE` from the environment at call time (not from `Settings`) so the
    decorator is independent of any Settings construction path.
    """

    @wraps(method)
    async def wrapper(self: Any, *args: Any, **kwargs: Any) -> _T:
        mode = os.environ.get("EXECUTION_MODE", "paper").lower()
        if mode != "live":
            raise PermissionError(
                f"{method.__qualname__} requires EXECUTION_MODE='live'; "
                f"got '{mode}'. Defence-in-depth per CLAUDE.md C3 / "
                f"SECURITY.md S3."
            )
        return await method(self, *args, **kwargs)

    return wrapper
