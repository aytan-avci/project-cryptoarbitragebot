"""Strategy protocol + the two helper protocols a strategy depends on.

Per `skills/arbitrage-detection/SKILL.md`:
- `Strategy.evaluate(view, clock) -> Opportunity | None` is PURE.
- `MarketView` is the strategy's window into current snapshots.
- `Clock` is the injected time provider (so strategies are deterministic
  under test and never touch `time.time()` or `datetime.now()`).

These two helper protocols live in `strategies/` (not `domain/`) because
they are interface contracts the strategy consumes, not transported data.
"""

from typing import Protocol, runtime_checkable

from arbitrage_agent.domain import (
    ExchangeId,
    MarketSnapshot,
    Opportunity,
    StrategyName,
    Symbol,
)


@runtime_checkable
class MarketView(Protocol):
    """Read-only view of the most-recent snapshots per (exchange, symbol)."""

    def snapshot(
        self, exchange: ExchangeId, symbol: Symbol
    ) -> MarketSnapshot | None:
        """Latest known snapshot, or `None` if absent / stale beyond TTL."""
        ...


@runtime_checkable
class Clock(Protocol):
    """Injectable time source. Strategies use this, never the stdlib `time`."""

    def now_ms(self) -> int:
        """Milliseconds since UNIX epoch, UTC."""
        ...


@runtime_checkable
class Strategy(Protocol):
    """A pure function from MarketView to (maybe) Opportunity."""

    name: StrategyName

    def evaluate(
        self, view: MarketView, clock: Clock
    ) -> Opportunity | None:
        """Emit an `Opportunity` if profitable AFTER fees + slippage; else
        `None`. Must not mutate `view` or `clock`, must not perform I/O."""
        ...
