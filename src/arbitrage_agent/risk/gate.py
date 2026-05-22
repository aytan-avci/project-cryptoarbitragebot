"""The risk gate — the **only** producer of `RiskDecision`.

Per `skills/risk-management/SKILL.md § The Cardinal Rule`: no order
reaches an exchange without `RiskDecision(approved=True)`. Any code
constructing a `RiskDecision` outside this module is an architectural
violation (static-analysis enforcement arrives in a later faz).

Coverage:
- Faz 5b — 6 checks deterministic from `(opportunity, limits, now_ms)`
  alone: kill_switch, freshness, profitability, min/max order value,
  gross exposure.
- Faz 7f — 3 more checks deterministic from `(opportunity, state,
  limits, now_ms)` with the orchestrator's `AccountStateTracker`
  populating `AccountState`: per-asset position cap, rolling
  orders/min counter, per-venue snapshot freshness (proxy for
  connectivity).
- Faz 7g — `min_required_balance` (deferred until balance reads from
  live adapters are wired into the tracker).

Pure function. No I/O. `now_ms` is **injected** so tests are
deterministic and the strategy module's purity rule extends here.
"""

from decimal import Decimal

from arbitrage_agent.domain import Opportunity, RiskDecision
from arbitrage_agent.risk.limits import AccountState, Limits


def _decision_age_ms(opportunity: Opportunity, now_ms: int) -> int:
    return now_ms - int(opportunity.detected_at.timestamp() * 1000)


def evaluate(
    opportunity: Opportunity,
    state: AccountState,
    limits: Limits,
    now_ms: int,
) -> RiskDecision:
    """Evaluate `opportunity` against current `state` and `limits`.

    First failing check stops the chain (SKILL.md § Decision Order).
    """
    opp_id = opportunity.id

    # 1. Kill-switch is engaged → reject
    if state.kill_switch_engaged:
        return RiskDecision(
            opportunity_id=opp_id,
            approved=False,
            reason="kill_switch_engaged",
        )

    # 2. Opportunity must be fresh (strategy declares its own shelf-life)
    age_ms = _decision_age_ms(opportunity, now_ms)
    if age_ms > opportunity.valid_for_ms:
        return RiskDecision(
            opportunity_id=opp_id,
            approved=False,
            reason=f"stale: age_ms={age_ms} > {opportunity.valid_for_ms}",
        )

    # 3. Profitability ≥ threshold
    if opportunity.expected_net_profit < limits.min_profit_threshold_usd:
        return RiskDecision(
            opportunity_id=opp_id,
            approved=False,
            reason=(
                f"profit_below_threshold: "
                f"{opportunity.expected_net_profit} < {limits.min_profit_threshold_usd}"
            ),
        )

    # 4–6. Per-leg and gross order-value bounds.
    leg_values = [leg.quantity * leg.limit_price for leg in opportunity.legs]
    if min(leg_values) < limits.min_order_value_usd:
        return RiskDecision(
            opportunity_id=opp_id,
            approved=False,
            reason=(
                f"leg_below_min_order_value: "
                f"min={min(leg_values)} < {limits.min_order_value_usd}"
            ),
        )
    if max(leg_values) > limits.max_order_value_usd:
        return RiskDecision(
            opportunity_id=opp_id,
            approved=False,
            reason=(
                f"leg_above_max_order_value: "
                f"max={max(leg_values)} > {limits.max_order_value_usd}"
            ),
        )
    if sum(leg_values) > limits.max_gross_exposure_usd:
        return RiskDecision(
            opportunity_id=opp_id,
            approved=False,
            reason=(
                f"gross_exposure_breach: "
                f"sum={sum(leg_values)} > {limits.max_gross_exposure_usd}"
            ),
        )

    # 7. Per-asset position cap — projected post-fill position value
    # must stay under the limit on every leg's (exchange, symbol) key.
    for leg in opportunity.legs:
        key = (leg.exchange, leg.symbol)
        current = Decimal(str(state.open_position_qty.get(key, "0")))
        delta = Decimal(str(leg.quantity))
        if leg.side == "sell":
            delta = -delta
        projected_qty = current + delta
        projected_value = abs(projected_qty) * Decimal(str(leg.limit_price))
        if projected_value > limits.max_position_value_usd:
            return RiskDecision(
                opportunity_id=opp_id,
                approved=False,
                reason=(
                    f"position_limit: {leg.exchange}/{leg.symbol} projected "
                    f"abs(qty)={projected_qty} × {leg.limit_price} = "
                    f"{projected_value} > {limits.max_position_value_usd}"
                ),
            )

    # 8. Rolling 60-second orders/minute cap.
    window_start_ms = now_ms - 60_000
    recent_in_window = sum(
        1 for t in state.recent_order_timestamps_ms if t > window_start_ms
    )
    projected_orders = recent_in_window + len(opportunity.legs)
    if projected_orders > limits.max_orders_per_minute:
        return RiskDecision(
            opportunity_id=opp_id,
            approved=False,
            reason=(
                f"orders_per_minute: projected={projected_orders} > "
                f"{limits.max_orders_per_minute} "
                f"(recent={recent_in_window}, legs={len(opportunity.legs)})"
            ),
        )

    # 9. Per-venue snapshot freshness (proxy for connectivity).
    # Absence of a venue from the tracking dict means freshness is not
    # yet wired (paper smoke, integration tests); the check is skipped
    # rather than failing closed.
    for leg in opportunity.legs:
        age = state.last_snapshot_age_ms_by_venue.get(leg.exchange)
        if age is not None and age > limits.max_snapshot_age_ms:
            return RiskDecision(
                opportunity_id=opp_id,
                approved=False,
                reason=(
                    f"venue_stale: {leg.exchange} last_snapshot_age_ms="
                    f"{age} > {limits.max_snapshot_age_ms}"
                ),
            )

    # 10. Min required balance per venue (Faz 7g-a).
    # Same "absent = unknown, skip" semantics as freshness: paper-smoke
    # and pre-balance-polling sessions don't track cash. Once
    # `tracker.set_cash(venue, amount)` runs (live mode balance
    # polling), the check bites.
    for leg in opportunity.legs:
        cash = state.cash_by_exchange.get(leg.exchange)
        if cash is not None and cash < limits.min_required_balance_usd:
            return RiskDecision(
                opportunity_id=opp_id,
                approved=False,
                reason=(
                    f"min_balance: {leg.exchange} cash={cash} < "
                    f"{limits.min_required_balance_usd}"
                ),
            )

    return RiskDecision(
        opportunity_id=opp_id,
        approved=True,
        reason="all checks passed",
    )
