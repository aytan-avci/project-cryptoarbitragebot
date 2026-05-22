"""Risk Layer state + limits — frozen data passed to the gate.

`AccountState` is the snapshot the gate evaluates against (positions, cash,
kill-switch, rolling-window order timestamps, per-venue snapshot ages).
`Limits` is the config-frozen policy (max position / exposure / rate /
freshness). Both are constructed by the orchestrator and passed in —
the gate never performs I/O (`skills/risk-management/SKILL.md § Anti-
Patterns`).
"""

from dataclasses import dataclass, field
from decimal import Decimal

from arbitrage_agent.config import Settings
from arbitrage_agent.domain import ExchangeId, Symbol, Volume


@dataclass(frozen=True, slots=True)
class AccountState:
    """Current account / position snapshot the gate evaluates against.

    Faz 7f added the last three fields; orchestrator's
    `AccountStateTracker` keeps them current.

    Dict / tuple fields are mutable-by-Python's-rules; treat their
    contents as read-only by convention until `MappingProxyType` wrap
    arrives in Faz 8+.
    """

    cash_by_exchange: dict[ExchangeId, Decimal] = field(default_factory=dict)
    open_position_qty: dict[tuple[ExchangeId, Symbol], Volume] = field(
        default_factory=dict
    )
    kill_switch_engaged: bool = False
    # Faz 7f additions
    recent_order_timestamps_ms: tuple[int, ...] = ()
    """Submission timestamps (ms since epoch) for orders in the recent
    past. The gate filters to a 60-second rolling window per check
    (SKILL.md § max_orders_per_minute)."""
    last_snapshot_age_ms_by_venue: dict[ExchangeId, int] = field(
        default_factory=dict
    )
    """Age in ms of the most recent snapshot per venue. Absence of a
    venue here means freshness is not yet tracked and the check is
    skipped (rather than rejecting blindly)."""


@dataclass(frozen=True, slots=True)
class Limits:
    """Frozen risk policy. Built once at startup from `Settings`.

    Freshness threshold of an `Opportunity` itself is NOT here —
    `opportunity.valid_for_ms` (set by the strategy) is the source of
    truth per SKILL.md § Decision Order.
    """

    min_profit_threshold_usd: Decimal
    min_order_value_usd: Decimal
    max_order_value_usd: Decimal
    max_gross_exposure_usd: Decimal
    # Faz 7f additions
    max_position_value_usd: Decimal
    max_orders_per_minute: int
    max_snapshot_age_ms: int
    # Faz 7g-a additions
    min_required_balance_usd: Decimal
    max_loss_per_day_usd: Decimal


def limits_from_settings(s: Settings) -> Limits:
    """Project the risk-related Settings fields into a `Limits` instance."""
    return Limits(
        min_profit_threshold_usd=s.risk_min_profit_threshold_usd,
        min_order_value_usd=s.risk_min_order_value_usd,
        max_order_value_usd=s.risk_max_order_value_usd,
        max_gross_exposure_usd=s.risk_max_gross_exposure_usd,
        max_position_value_usd=s.risk_max_position_value_usd,
        max_orders_per_minute=s.risk_max_orders_per_minute,
        max_snapshot_age_ms=s.risk_max_snapshot_age_ms,
        min_required_balance_usd=s.risk_min_required_balance_usd,
        max_loss_per_day_usd=s.risk_max_loss_per_day_usd,
    )
