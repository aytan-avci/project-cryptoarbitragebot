"""Domain identifier types. Stdlib only."""

from dataclasses import dataclass
from typing import NewType
from uuid import uuid4

ExchangeId = NewType("ExchangeId", str)
OpportunityId = NewType("OpportunityId", str)
OrderId = NewType("OrderId", str)
Asset = NewType("Asset", str)  # single currency code, e.g. Asset("BTC")


@dataclass(frozen=True, slots=True)
class Symbol:
    """Trading pair, e.g. Symbol("BTC", "USDT") for BTC/USDT."""

    base: str
    quote: str

    @classmethod
    def from_string(cls, s: str) -> "Symbol":
        """Parse 'BASE/QUOTE'. Both halves are upper-cased."""
        parts = s.split("/")
        if len(parts) != 2:
            raise ValueError(f"Symbol must be 'BASE/QUOTE', got: {s!r}")
        base, quote = parts
        return cls(base=base.upper(), quote=quote.upper())

    def __str__(self) -> str:
        return f"{self.base}/{self.quote}"


def new_opportunity_id() -> OpportunityId:
    """Factory: random UUID4 opportunity id."""
    return OpportunityId(str(uuid4()))


def new_order_id() -> OrderId:
    """Factory: random UUID4 order id."""
    return OrderId(str(uuid4()))
