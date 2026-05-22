"""Execution Engine — concurrent leg placement + per-leg timeout +
state-machine classification (Faz 7e).

Per `skills/execution-engine/SKILL.md § Placing an Opportunity`:
1. Validate `RiskDecision` (approved + opportunity_id match).
2. Submit every leg concurrently (asyncio.gather).
3. Each leg has its own timeout = `opportunity.valid_for_ms`. After
   the timeout, the inner submission is cancelled; the leg is marked
   `failed` so the reconciler / hedger can flag the imbalance.
4. After all legs settle, classify each via `reconciler.classify_leg`.
5. Return `ExecutionResult` for the caller (pipeline + hedger) to
   inspect.

Faz 7e deferred: idempotent retry on network failure (would need
pre-generated client_order_id + fetch_order_by_client_id — both Faz
7e+).
"""

import asyncio

import structlog

from arbitrage_agent.domain import (
    ExchangeId,
    ExecutionResult,
    Fill,
    LegResult,
    Opportunity,
    OrderId,
    OrderIntent,
    RiskDecision,
)
from arbitrage_agent.exchanges.base import ExchangeAdapter
from arbitrage_agent.execution.reconciler import classify_leg

_log = structlog.get_logger()


async def _submit_one_leg(
    leg: OrderIntent,
    opportunity: Opportunity,
    decision: RiskDecision,
    adapter: ExchangeAdapter,
    timeout_s: float,
) -> LegResult:
    """Place a single leg with its own deadline. Return a LegResult
    that captures the order_id (if any), the terminal state, and any
    fills observed before timeout."""
    error: Exception | None = None
    order_id: OrderId | None = None
    fills: list[Fill] = []

    async def _do_submit() -> OrderId:
        return await adapter.place_order(leg, decision)

    try:
        order_id = await asyncio.wait_for(_do_submit(), timeout=timeout_s)
    except asyncio.TimeoutError:
        error = TimeoutError(
            f"leg timed out after {timeout_s:.3f}s (opp.valid_for_ms = "
            f"{opportunity.valid_for_ms})"
        )
    except asyncio.CancelledError:
        raise
    except Exception as exc:  # noqa: BLE001 — adapter exceptions captured per-leg
        error = exc

    # Collect any fills the adapter recorded for this opportunity.
    # PaperExchange returns synthetic instant fills; live adapters
    # return whatever has been observed via REST/WS so far.
    if error is None:
        try:
            fills = await asyncio.wait_for(
                adapter.fetch_fills(since=opportunity.detected_at),
                timeout=timeout_s,
            )
        except (asyncio.TimeoutError, asyncio.CancelledError):
            raise
        except (NotImplementedError, PermissionError):
            fills = []  # paper-mode live adapters can't fetch_fills; accept
        except Exception as exc:  # noqa: BLE001
            # Placement succeeded but fill retrieval failed — keep order_id,
            # mark failure.
            error = exc

    # Filter to fills that match this leg's symbol AND opportunity_id.
    leg_fills = tuple(
        f for f in fills
        if f.symbol == leg.symbol and f.opportunity_id == opportunity.id
    )

    state = classify_leg(leg, error, leg_fills)

    return LegResult(
        leg=leg,
        order_id=order_id,
        state=state,
        fills=leg_fills,
        error_message=None if error is None else f"{type(error).__name__}: {error}",
    )


async def execute(
    opportunity: Opportunity,
    decision: RiskDecision,
    adapters: dict[ExchangeId, ExchangeAdapter],
) -> ExecutionResult:
    """Place every leg of `opportunity` via the matching adapter,
    concurrently, with per-leg timeout. Returns an `ExecutionResult`.

    Raises:
        ValueError: decision not approved.
        ValueError: decision.opportunity_id ≠ opportunity.id.
        KeyError: an adapter for one of the leg exchanges is missing.
    """
    if not decision.approved:
        raise ValueError(
            f"execute requires approved decision; got reason={decision.reason!r}"
        )
    if decision.opportunity_id != opportunity.id:
        raise ValueError(
            f"opportunity_id mismatch: decision={decision.opportunity_id!r} "
            f"opp={opportunity.id!r}"
        )

    # Pre-validate every leg has an adapter — fail fast before any
    # placement, so we don't leave half the legs submitted.
    for leg in opportunity.legs:
        if leg.exchange not in adapters:
            raise KeyError(leg.exchange)

    timeout_s = opportunity.valid_for_ms / 1000.0

    coros = [
        _submit_one_leg(leg, opportunity, decision, adapters[leg.exchange], timeout_s)
        for leg in opportunity.legs
    ]
    leg_results = await asyncio.gather(*coros)

    result = ExecutionResult(
        opportunity_id=opportunity.id,
        legs=tuple(leg_results),
    )

    _log.info(
        "execution.completed",
        opportunity_id=result.opportunity_id,
        all_filled=result.all_filled,
        needs_hedge=result.needs_hedge,
        states=[lr.state for lr in result.legs],
    )

    return result
