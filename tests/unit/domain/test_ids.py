import uuid
from dataclasses import FrozenInstanceError

import pytest

from arbitrage_agent.domain.ids import (
    ExchangeId,
    Symbol,
    new_opportunity_id,
    new_order_id,
)


class TestSymbol:
    def test_from_string_basic(self):
        s = Symbol.from_string("BTC/USDT")
        assert s.base == "BTC"
        assert s.quote == "USDT"

    def test_from_string_normalizes_case(self):
        s = Symbol.from_string("btc/usdt")
        assert s.base == "BTC"
        assert s.quote == "USDT"

    def test_from_string_rejects_no_separator(self):
        with pytest.raises(ValueError):
            Symbol.from_string("BTCUSDT")

    def test_from_string_rejects_multiple_separators(self):
        with pytest.raises(ValueError):
            Symbol.from_string("A/B/C")

    def test_str_roundtrip(self):
        s = Symbol.from_string("ETH/USDC")
        assert str(s) == "ETH/USDC"

    def test_frozen(self):
        s = Symbol("BTC", "USDT")
        with pytest.raises(FrozenInstanceError):
            s.base = "ETH"  # type: ignore[misc]

    def test_value_equality(self):
        assert Symbol("BTC", "USDT") == Symbol("BTC", "USDT")
        assert Symbol("BTC", "USDT") != Symbol("ETH", "USDT")

    def test_hashable(self):
        # frozen + slots ⇒ usable as dict key / set member
        s1, s2 = Symbol("BTC", "USDT"), Symbol("BTC", "USDT")
        assert hash(s1) == hash(s2)
        assert {s1, s2} == {s1}


class TestExchangeId:
    def test_constructs_from_string(self):
        eid: ExchangeId = ExchangeId("binance")
        assert eid == "binance"


class TestOpportunityId:
    def test_factory_returns_unique_ids(self):
        a = new_opportunity_id()
        b = new_opportunity_id()
        assert a != b

    def test_factory_returns_valid_uuid4(self):
        x = new_opportunity_id()
        uuid.UUID(x)  # raises if malformed


class TestOrderId:
    def test_factory_returns_unique_ids(self):
        a = new_order_id()
        b = new_order_id()
        assert a != b

    def test_factory_returns_valid_uuid4(self):
        x = new_order_id()
        uuid.UUID(x)

    def test_distinct_from_opportunity_id_namespace(self):
        # Both are NewType[str]; runtime values are independent random UUIDs.
        assert new_order_id() != new_opportunity_id()
