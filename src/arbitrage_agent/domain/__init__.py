"""Domain types — pure data, zero deps on other `arbitrage_agent` modules.

This package may import from stdlib only. Anything else is a bug
(`specs/PROJECT_STRUCTURE.md § Rules`). Field names and shapes are
normative per `specs/ARCHITECTURE.md § 6`.
"""

from arbitrage_agent.domain.events import (
    ExecutionResult,
    Fill,
    HedgeResult,
    HedgeStatus,
    LegResult,
    MarketSnapshot,
    Opportunity,
    OrderIntent,
    OrderSide,
    OrderState,
    RiskDecision,
    StrategyName,
    now_utc,
)
from arbitrage_agent.domain.ids import (
    Asset,
    ExchangeId,
    OpportunityId,
    OrderId,
    Symbol,
    new_opportunity_id,
    new_order_id,
)
from arbitrage_agent.domain.money import Price, Volume, price, volume

__all__ = [
    "Asset",
    "ExchangeId",
    "ExecutionResult",
    "Fill",
    "HedgeResult",
    "HedgeStatus",
    "LegResult",
    "MarketSnapshot",
    "Opportunity",
    "OpportunityId",
    "OrderId",
    "OrderIntent",
    "OrderSide",
    "OrderState",
    "Price",
    "RiskDecision",
    "StrategyName",
    "Symbol",
    "Volume",
    "new_opportunity_id",
    "new_order_id",
    "now_utc",
    "price",
    "volume",
]
