"""Domain events — what flows between modules.

    MarketSnapshot      ingestion → strategy
    Opportunity         strategy  → risk
    RiskDecision        risk      → execution
    Fill                execution → persistence

`OrderIntent` is the leg-level building block of an Opportunity.

Field names and shapes are normative per `specs/ARCHITECTURE.md § 6`.
Stdlib only (sibling-module imports within `domain/` are allowed).
"""

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from typing import Literal

from arbitrage_agent.domain.ids import ExchangeId, OpportunityId, Symbol
from arbitrage_agent.domain.money import Price, Volume

OrderSide = Literal["buy", "sell"]
StrategyName = Literal["spatial", "triangular", "funding"]

# Order lifecycle states per `skills/execution-engine/SKILL.md`.
# `pending`   — created from RiskDecision, not yet sent.
# `submitted` — adapter returned an order_id, no fills observed yet.
# `partial`   — exchange reports some quantity filled, < intent.quantity.
# `filled`    — fully filled (terminal, good).
# `cancelled` — operator/timeout cancelled (terminal).
# `rejected`  — exchange refused (terminal, bad — reason logged).
# `failed`    — network or unknown error (terminal, reconciliation needed).
OrderState = Literal[
    "pending", "submitted", "partial", "filled", "cancelled", "rejected", "failed",
]


def now_utc() -> datetime:
    """Timezone-aware UTC timestamp. Use for every domain timestamp."""
    return datetime.now(timezone.utc)


@dataclass(frozen=True, slots=True)
class OrderIntent:
    """One leg of an Opportunity. Always limit-priced (no market orders in MVP)."""

    exchange: ExchangeId
    symbol: Symbol
    side: OrderSide
    quantity: Volume
    limit_price: Price


@dataclass(frozen=True, slots=True)
class MarketSnapshot:
    exchange: ExchangeId
    symbol: Symbol
    bid: Price
    ask: Price
    bid_size: Volume
    ask_size: Volume
    timestamp_utc: datetime


@dataclass(frozen=True, slots=True)
class Opportunity:
    id: OpportunityId
    detected_at: datetime
    strategy: StrategyName
    legs: tuple[OrderIntent, ...]
    expected_net_profit: Decimal  # AFTER fees + slippage; risk module's gate
    confidence: float  # in [0, 1]
    valid_for_ms: int  # shelf-life — risk gate rejects past this age


@dataclass(frozen=True, slots=True)
class RiskDecision:
    """Risk Layer's verdict on an Opportunity. The gate to execution.

    `reason` is required even on approve — every decision must be auditable.
    `adjusted_quantity` may downsize an intent's quantity, never upsize it.
    """

    opportunity_id: OpportunityId
    approved: bool
    reason: str
    adjusted_quantity: Volume | None = None


@dataclass(frozen=True, slots=True)
class Fill:
    opportunity_id: OpportunityId
    exchange: ExchangeId
    symbol: Symbol
    side: OrderSide
    price: Price
    volume: Volume
    fee: Price
    timestamp_utc: datetime


@dataclass(frozen=True, slots=True)
class LegResult:
    """Per-leg outcome of executing an `Opportunity` (Faz 7e).

    `state` is the terminal state per `skills/execution-engine/SKILL.md`.
    `fills` is the list of fills observed by the adapter for this leg.
    `error_message` is non-None when state ∈ {rejected, failed}.
    `order_id` is None only when placement itself failed (no order id
    was ever returned).
    """

    leg: "OrderIntent"
    order_id: "OpportunityId | None"  # using string-typed for forward-ref simplicity
    state: OrderState
    fills: tuple[Fill, ...] = ()
    error_message: str | None = None


@dataclass(frozen=True, slots=True)
class ExecutionResult:
    """Outcome of `execution.engine.execute(opportunity, decision, adapters)`."""

    opportunity_id: OpportunityId
    legs: tuple[LegResult, ...]

    @property
    def all_filled(self) -> bool:
        return all(leg.state == "filled" for leg in self.legs)

    @property
    def needs_hedge(self) -> bool:
        """Any non-fully-filled leg means inventory is unbalanced."""
        return any(leg.state in ("partial", "rejected", "failed", "cancelled")
                   for leg in self.legs)


HedgeStatus = Literal[
    "no_imbalance",       # legs net to zero — no hedge needed
    "filled",             # counter-leg placed and fully filled
    "partial",            # counter-leg placed, partial fill — residual exposure logged
    "aborted_slippage",   # market drifted past budget; no order placed
    "no_market_data",     # missing snapshot for counter-leg venue
    "placement_failed",   # adapter raised on place_order
]


@dataclass(frozen=True, slots=True)
class HedgeResult:
    """Outcome of `execution.hedger.hedge(...)` (Faz 7g-c).

    `counter_leg` is the OrderIntent the hedger placed (or would have);
    None when status ∈ {no_imbalance, no_market_data}. `fills` is what
    the counter-leg returned, if any. `remaining_exposure` is the
    signed quantity still un-hedged after the attempt (zero on success).
    """

    opportunity_id: OpportunityId
    status: HedgeStatus
    counter_leg: "OrderIntent | None"
    fills: tuple[Fill, ...] = ()
    remaining_exposure: Decimal = Decimal("0")
    reason: str = ""
