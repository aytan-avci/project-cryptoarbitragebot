"""Reconcile expected vs actual fills per leg.

Pure classifier: given the leg intent, an optional adapter error, and
the observed fills, return the terminal `OrderState`. Saves the engine
from carrying that logic inline; makes the rules testable in isolation
(Karpathy 1.2 — small, deterministic, no I/O).

Per `skills/execution-engine/SKILL.md § The Order Lifecycle State
Machine`: terminal states are FILLED / PARTIAL / CANCELLED / REJECTED /
FAILED. PENDING and SUBMITTED are transitional (not returned here —
they would mean the engine never reached classification).
"""

from decimal import Decimal

from arbitrage_agent.domain import Fill, OrderIntent, OrderState
from arbitrage_agent.exchanges.errors import (
    InvalidOrder,
    MarketHalted,
    PermanentFailure,
    RateLimited,
    TemporaryFailure,
)


def classify_leg(
    intent: OrderIntent,
    error: Exception | None,
    fills: list[Fill] | tuple[Fill, ...],
) -> OrderState:
    """Determine the terminal state of a leg from the adapter's response.

    Priority:
    1. Adapter raised an exception → REJECTED (exchange said no) or
       FAILED (network / unknown).
    2. Volume filled == intent.quantity → FILLED.
    3. 0 < filled < intent.quantity → PARTIAL.
    4. Filled == 0 with no error → CANCELLED (timeout-cancelled, or
       no fill arrived within the wait window; the engine cancelled
       the open order before classification).
    """
    if error is not None:
        # Exchange-side refusal ⇒ REJECTED. Network / unknown ⇒ FAILED.
        if isinstance(error, (InvalidOrder, MarketHalted, PermanentFailure)):
            return "rejected"
        if isinstance(error, (RateLimited, TemporaryFailure)):
            return "failed"
        # Unknown exception class — be conservative: FAILED requires
        # reconciliation, REJECTED is "exchange-final"; we don't know.
        return "failed"

    filled = sum(
        (Decimal(str(f.volume)) for f in fills),
        start=Decimal("0"),
    )
    intended = Decimal(str(intent.quantity))
    if filled >= intended:
        return "filled"
    if filled > 0:
        return "partial"
    return "cancelled"
