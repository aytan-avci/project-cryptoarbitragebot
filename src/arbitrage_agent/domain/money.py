"""Monetary primitives. Decimal-based; floats are rejected at construction.

Stdlib only.
"""

from decimal import Decimal
from typing import NewType

Price = NewType("Price", Decimal)
Volume = NewType("Volume", Decimal)


def price(value: str | Decimal) -> Price:
    """Construct a Price from a Decimal or its string representation.

    Floats are rejected by the type system — never pass a float to this
    factory. Decimal(float) silently introduces binary-fraction error.
    """
    return Price(value if isinstance(value, Decimal) else Decimal(value))


def volume(value: str | Decimal) -> Volume:
    """Construct a Volume from a Decimal or its string representation."""
    return Volume(value if isinstance(value, Decimal) else Decimal(value))
