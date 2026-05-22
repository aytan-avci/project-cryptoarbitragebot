"""Hedger — recovery path when a leg fails to fully fill (Faz 7g-c).

Per `skills/execution-engine/SKILL.md § The Hedger`: when inventory is
unbalanced the hedger's job is to **return to neutral**, accepting a
degraded P&L on that opportunity.

Faz 7g-c upgrade: real implementation.

1. **Best-effort cancel** of any partial/failed leg whose `order_id`
   we still hold — keeps an exchange-side order from continuing to fill
   into our exposure.
2. **Compute signed net exposure** from observed fills (`buy=+vol`,
   `sell=-vol`) aggregated per `Symbol`.
3. **Build a counter-leg** opposite the net exposure on the venue
   where the failed leg was supposed to land (or, lacking that, the
   venue with the freshest book on the symbol).
4. **Slippage budget gate**: compare current best price for the
   counter-leg's side against the *fair price* (the average of the
   filled side that we now need to unwind). If drift > budget
   (`hedge_max_slippage_bps`), abort — emit `hedger.aborted_slippage`
   with the open exposure for the operator to handle.
5. **Synthesize a hedge `RiskDecision`** with `reason="hedge for
   opportunity X"` (SKILL.md: hedger is the only code that may submit
   without an upstream opportunity-bound decision).
6. **Place** the counter-leg via the chosen adapter. Fetch fills.
   Re-compute net; report remaining exposure (zero on success).

Hedger NEVER:
- runs without a budget,
- waits for the operator before cancelling open orders that are
  growing our exposure,
- places a hedge against an opportunity it can't price (no snapshot →
  status="no_market_data", surfaced for the operator).
"""

from __future__ import annotations

from decimal import Decimal

import structlog

from arbitrage_agent.domain import (
    ExchangeId,
    ExecutionResult,
    HedgeResult,
    LegResult,
    OrderIntent,
    Opportunity,
    OrderSide,
    Price,
    RiskDecision,
    Symbol,
    Volume,
)
from arbitrage_agent.exchanges.base import ExchangeAdapter
from arbitrage_agent.ingestion.bus import LatestSnapshotView

_log = structlog.get_logger()

_BPS_DIVISOR = Decimal("10000")


# ---- Pure helpers ---------------------------------------------------------


def compute_net_exposure(result: ExecutionResult) -> dict[Symbol, Decimal]:
    """Signed sum of observed fills per symbol.

    `buy` adds to the position, `sell` subtracts. Returns symbols with
    non-zero net only. Pure: no I/O, no mutation."""
    nets: dict[Symbol, Decimal] = {}
    for leg in result.legs:
        for fill in leg.fills:
            sign = Decimal("1") if fill.side == "buy" else Decimal("-1")
            nets[fill.symbol] = nets.get(fill.symbol, Decimal("0")) + sign * Decimal(str(fill.volume))
    return {sym: net for sym, net in nets.items() if net != 0}


def _pick_failed_leg(result: ExecutionResult, symbol: Symbol) -> LegResult | None:
    """The first non-`filled` leg on the given symbol — its venue is the
    natural place for the counter-leg (we were going to trade there
    anyway, so credentials + connectivity are already proven)."""
    for leg in result.legs:
        if leg.leg.symbol == symbol and leg.state != "filled":
            return leg
    return None


def _average_fill_price(result: ExecutionResult, symbol: Symbol, side: OrderSide) -> Decimal | None:
    """Volume-weighted average price across all fills on the SIDE we now
    need to unwind. Used as the slippage reference. None if no fills
    matched (caller falls back to snapshot mid)."""
    total_vol = Decimal("0")
    total_notional = Decimal("0")
    for leg in result.legs:
        for fill in leg.fills:
            if fill.symbol != symbol or fill.side != side:
                continue
            vol = Decimal(str(fill.volume))
            total_vol += vol
            total_notional += vol * Decimal(str(fill.price))
    if total_vol == 0:
        return None
    return total_notional / total_vol


def _within_slippage(
    fair: Decimal, market: Decimal, side: OrderSide, max_bps: int
) -> bool:
    """For a counter-leg `side`, is `market` within `max_bps` of `fair`?

    - Hedge sell: drift = (fair - market) / fair — selling lower than
      we bought eats P&L. Bad if drift > budget.
    - Hedge buy:  drift = (market - fair) / fair — buying back higher
      than we sold eats P&L. Bad if drift > budget.
    """
    if fair <= 0:
        return False
    budget = Decimal(max_bps) / _BPS_DIVISOR
    if side == "sell":
        drift = (fair - market) / fair
    else:
        drift = (market - fair) / fair
    return drift <= budget


# ---- Orchestration --------------------------------------------------------


async def _best_effort_cancel(
    result: ExecutionResult,
    adapters: dict[ExchangeId, ExchangeAdapter],
) -> None:
    """Cancel any non-terminal-good leg's order. Failures are logged
    and swallowed — by the time we're hedging, the order may already be
    cancelled, may never have been accepted, or the venue may be down.
    None of those should block neutralisation of the position we have."""
    for leg in result.legs:
        if leg.state == "filled" or leg.order_id is None:
            continue
        adapter = adapters.get(leg.leg.exchange)
        if adapter is None:
            continue
        try:
            await adapter.cancel_order(leg.order_id)
        except (NotImplementedError, PermissionError):
            continue  # paper / wrong-mode
        except Exception as exc:  # noqa: BLE001 — best-effort
            _log.warning(
                "hedger.cancel_failed",
                exchange=leg.leg.exchange,
                order_id=leg.order_id,
                error=f"{type(exc).__name__}: {exc}",
            )


async def hedge(
    opportunity: Opportunity,
    result: ExecutionResult,
    adapters: dict[ExchangeId, ExchangeAdapter],
    view: LatestSnapshotView,
    max_slippage_bps: int,
) -> HedgeResult:
    """Neutralise the un-hedged exposure from `result`.

    Returns a `HedgeResult` capturing the outcome. The pipeline records
    `result.fills` to the audit log + tracker exactly like the original
    execution fills, so the audit trail covers both phases."""

    # Step 0: imbalance check.
    nets = compute_net_exposure(result)
    if not nets:
        return HedgeResult(
            opportunity_id=result.opportunity_id,
            status="no_imbalance",
            counter_leg=None,
            remaining_exposure=Decimal("0"),
            reason="all legs net to zero",
        )

    # MVP: handle a single-symbol imbalance (spatial). Triangular hedge
    # across multiple symbols lands when that strategy ships.
    symbol, net = next(iter(nets.items()))

    # Step 1: try to cancel anything still alive so it stops adding to net.
    await _best_effort_cancel(result, adapters)

    # Step 2: pick venue + counter-side.
    failed_leg = _pick_failed_leg(result, symbol)
    counter_side: OrderSide = "sell" if net > 0 else "buy"
    counter_qty = abs(net)
    counter_venue: ExchangeId | None = failed_leg.leg.exchange if failed_leg else None

    # If no failed leg (rare: all legs filled but net non-zero — partial
    # fills on a "filled" classification shouldn't happen, but be defensive):
    # take any adapter that has a snapshot on the symbol.
    if counter_venue is None:
        for ex_id in adapters:
            if view.snapshot(ex_id, symbol) is not None:
                counter_venue = ex_id
                break

    if counter_venue is None or counter_venue not in adapters:
        return HedgeResult(
            opportunity_id=result.opportunity_id,
            status="no_market_data",
            counter_leg=None,
            remaining_exposure=net,
            reason="no adapter or snapshot available for counter-leg venue",
        )

    snap = view.snapshot(counter_venue, symbol)
    if snap is None:
        return HedgeResult(
            opportunity_id=result.opportunity_id,
            status="no_market_data",
            counter_leg=None,
            remaining_exposure=net,
            reason=f"no snapshot for {counter_venue} {symbol}",
        )

    # Reference for slippage: the average price at which we built the
    # position we now need to unwind. The unwind side is the OPPOSITE
    # of counter_side (we filled on `unwound_side`, now we hedge with
    # `counter_side`). For a long net position (net>0, counter_side=sell)
    # the fair price comes from the BUY fills.
    unwound_side: OrderSide = "buy" if counter_side == "sell" else "sell"
    fair = _average_fill_price(result, symbol, unwound_side)
    if fair is None:
        # Defensive: net non-zero but no fills on the unwind side. Use
        # snapshot mid as a last-resort reference.
        fair = (Decimal(str(snap.bid)) + Decimal(str(snap.ask))) / Decimal("2")

    market = Decimal(str(snap.bid if counter_side == "sell" else snap.ask))

    if not _within_slippage(fair, market, counter_side, max_slippage_bps):
        _log.warning(
            "hedger.aborted_slippage",
            opportunity_id=result.opportunity_id,
            symbol=str(symbol),
            counter_venue=counter_venue,
            counter_side=counter_side,
            fair_price=str(fair),
            market_price=str(market),
            max_slippage_bps=max_slippage_bps,
            remaining_exposure=str(net),
            action_required="operator manually neutralise",
        )
        return HedgeResult(
            opportunity_id=result.opportunity_id,
            status="aborted_slippage",
            counter_leg=None,
            remaining_exposure=net,
            reason=(
                f"market {market} drifted beyond {max_slippage_bps}bps of fair {fair}"
            ),
        )

    counter_intent = OrderIntent(
        exchange=counter_venue,
        symbol=symbol,
        side=counter_side,
        quantity=Volume(counter_qty),
        limit_price=Price(market),
    )

    hedge_decision = RiskDecision(
        opportunity_id=opportunity.id,
        approved=True,
        reason=f"hedge for opportunity {opportunity.id}",
    )

    adapter = adapters[counter_venue]
    try:
        order_id = await adapter.place_order(counter_intent, hedge_decision)
    except Exception as exc:  # noqa: BLE001
        _log.error(
            "hedger.placement_failed",
            opportunity_id=result.opportunity_id,
            counter_venue=counter_venue,
            error=f"{type(exc).__name__}: {exc}",
            remaining_exposure=str(net),
        )
        return HedgeResult(
            opportunity_id=result.opportunity_id,
            status="placement_failed",
            counter_leg=counter_intent,
            remaining_exposure=net,
            reason=f"{type(exc).__name__}: {exc}",
        )

    # Fetch fills for the counter-leg. Filter to the symbol AND the
    # opportunity_id we tagged on the synthetic RiskDecision — both
    # PaperExchange and Binance honour that tagging path.
    try:
        all_fills = await adapter.fetch_fills(since=opportunity.detected_at)
    except (NotImplementedError, PermissionError):
        all_fills = []

    hedge_fills = tuple(
        f for f in all_fills
        if f.symbol == symbol
        and f.opportunity_id == opportunity.id
        and f.side == counter_side
        and f not in {fl for lr in result.legs for fl in lr.fills}
    )

    # Recompute net after the hedge fills.
    hedged_volume = sum(
        (Decimal(str(f.volume)) for f in hedge_fills),
        start=Decimal("0"),
    )
    remaining = net - (hedged_volume if counter_side == "sell" else -hedged_volume)
    status = "filled" if remaining == 0 else "partial"

    _log.info(
        "hedger.completed",
        opportunity_id=result.opportunity_id,
        status=status,
        counter_venue=counter_venue,
        counter_side=counter_side,
        counter_qty=str(counter_qty),
        fair_price=str(fair),
        executed_price=str(market),
        order_id=order_id,
        hedge_fills=len(hedge_fills),
        remaining_exposure=str(remaining),
    )

    return HedgeResult(
        opportunity_id=result.opportunity_id,
        status=status,
        counter_leg=counter_intent,
        fills=hedge_fills,
        remaining_exposure=remaining,
        reason=(
            f"placed {counter_side} {counter_qty} {symbol} @ {market} on {counter_venue}"
        ),
    )


# ---- Backwards-compatible observability hook ------------------------------


def needs_hedge(result: ExecutionResult) -> bool:
    """True if any leg is in a non-fully-filled terminal state."""
    return result.needs_hedge


# Kept as a tiny structured-event hook for callers that want to log
# before invoking the real hedger (Faz 7e behaviour). The pipeline no
# longer calls this; tests still reference it for the legacy alert
# shape.
def emit_hedge_alert(result: ExecutionResult) -> None:
    """Log a structured `hedger.imbalance_detected` event with leg
    details. Useful as a diagnostic step before the active hedge."""
    if not result.needs_hedge:
        return
    bad_legs = [
        {
            "exchange": leg.leg.exchange,
            "symbol": str(leg.leg.symbol),
            "side": leg.leg.side,
            "intended_qty": str(leg.leg.quantity),
            "state": leg.state,
            "error": leg.error_message,
            "filled_qty": str(sum((f.volume for f in leg.fills), start=type(leg.leg.quantity)("0"))),
        }
        for leg in result.legs
        if leg.state in ("partial", "rejected", "failed", "cancelled")
    ]
    _log.warning(
        "hedger.imbalance_detected",
        opportunity_id=result.opportunity_id,
        legs=bad_legs,
    )
