from decimal import Decimal, InvalidOperation

import pytest

from arbitrage_agent.domain.money import price, volume


class TestPrice:
    def test_from_string(self):
        p = price("100.50")
        assert isinstance(p, Decimal)
        assert p == Decimal("100.50")

    def test_from_decimal(self):
        p = price(Decimal("100.50"))
        assert p == Decimal("100.50")

    def test_preserves_satoshi_precision(self):
        p = price("0.00000001")
        assert p == Decimal("0.00000001")

    def test_arithmetic(self):
        # Type-erased at runtime (NewType is compile-time); Decimal math holds.
        a, b = price("100.10"), price("0.05")
        assert a + b == Decimal("100.15")

    def test_invalid_string_raises(self):
        with pytest.raises(InvalidOperation):
            price("not-a-number")


class TestVolume:
    def test_from_string(self):
        v = volume("0.5")
        assert v == Decimal("0.5")

    def test_from_decimal(self):
        v = volume(Decimal("12.34"))
        assert v == Decimal("12.34")
