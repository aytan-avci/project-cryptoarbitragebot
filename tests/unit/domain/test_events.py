from dataclasses import FrozenInstanceError
from datetime import datetime, timezone
from decimal import Decimal

import pytest

from arbitrage_agent.domain.events import (
    Fill,
    MarketSnapshot,
    Opportunity,
    OrderIntent,
    RiskDecision,
    now_utc,
)
from arbitrage_agent.domain.ids import (
    ExchangeId,
    Symbol,
    new_opportunity_id,
)
from arbitrage_agent.domain.money import price, volume


def test_now_utc_is_tz_aware_utc():
    t = now_utc()
    assert t.tzinfo is not None
    assert t.utcoffset() == timezone.utc.utcoffset(t)
    assert isinstance(t, datetime)


# ---------- MarketSnapshot ----------

def _make_snapshot() -> MarketSnapshot:
    return MarketSnapshot(
        exchange=ExchangeId("binance"),
        symbol=Symbol("BTC", "USDT"),
        bid=price("60000.00"),
        ask=price("60001.00"),
        bid_size=volume("0.5"),
        ask_size=volume("0.3"),
        timestamp_utc=now_utc(),
    )


class TestMarketSnapshot:
    def test_constructs(self):
        snap = _make_snapshot()
        assert snap.exchange == "binance"
        assert snap.symbol.base == "BTC"
        assert snap.bid < snap.ask

    def test_frozen(self):
        snap = _make_snapshot()
        with pytest.raises(FrozenInstanceError):
            snap.bid = price("0")  # type: ignore[misc]

    def test_uses_spec_field_names(self):
        # Regression guard against drifting back to pre-reconciliation names.
        snap = _make_snapshot()
        for f in ("bid_size", "ask_size", "timestamp_utc"):
            assert hasattr(snap, f), f
        for f in ("bid_volume", "ask_volume", "timestamp"):
            assert not hasattr(snap, f), f


# ---------- OrderIntent ----------

def _make_intent(side: str = "buy") -> OrderIntent:
    return OrderIntent(
        exchange=ExchangeId("binance"),
        symbol=Symbol("BTC", "USDT"),
        side=side,  # type: ignore[arg-type]
        quantity=volume("0.01"),
        limit_price=price("60000.00"),
    )


class TestOrderIntent:
    def test_constructs_buy(self):
        intent = _make_intent("buy")
        assert intent.side == "buy"
        assert intent.quantity == Decimal("0.01")
        assert intent.limit_price == Decimal("60000.00")

    def test_constructs_sell(self):
        intent = _make_intent("sell")
        assert intent.side == "sell"

    def test_frozen(self):
        intent = _make_intent()
        with pytest.raises(FrozenInstanceError):
            intent.quantity = volume("0")  # type: ignore[misc]

    def test_hashable(self):
        a, b = _make_intent("buy"), _make_intent("buy")
        assert hash(a) == hash(b)


# ---------- Opportunity ----------

class TestOpportunity:
    def test_constructs_spatial_two_legs(self):
        opp = Opportunity(
            id=new_opportunity_id(),
            detected_at=now_utc(),
            strategy="spatial",
            legs=(_make_intent("buy"), _make_intent("sell")),
            expected_net_profit=Decimal("12.34"),
            confidence=0.85,
            valid_for_ms=1000,
        )
        assert opp.strategy == "spatial"
        assert len(opp.legs) == 2
        assert opp.expected_net_profit == Decimal("12.34")
        assert 0.0 <= opp.confidence <= 1.0

    def test_constructs_triangular_three_legs(self):
        legs = (_make_intent("buy"), _make_intent("sell"), _make_intent("buy"))
        opp = Opportunity(
            id=new_opportunity_id(),
            detected_at=now_utc(),
            strategy="triangular",
            legs=legs,
            expected_net_profit=Decimal("5.00"),
            confidence=0.7,
            valid_for_ms=500,
        )
        assert len(opp.legs) == 3

    def test_legs_is_immutable_tuple(self):
        opp = Opportunity(
            id=new_opportunity_id(),
            detected_at=now_utc(),
            strategy="spatial",
            legs=(_make_intent(),),
            expected_net_profit=Decimal("1.00"),
            confidence=0.5,
            valid_for_ms=1000,
        )
        assert isinstance(opp.legs, tuple)

    def test_frozen(self):
        opp = Opportunity(
            id=new_opportunity_id(),
            detected_at=now_utc(),
            strategy="spatial",
            legs=(_make_intent(),),
            expected_net_profit=Decimal("1.00"),
            confidence=0.5,
            valid_for_ms=1000,
        )
        with pytest.raises(FrozenInstanceError):
            opp.confidence = 0.0  # type: ignore[misc]

    def test_valid_for_ms_spec_field(self):
        """Regression guard: SKILL.md mandates `valid_for_ms` on every
        Opportunity. Removing it silently breaks the risk gate's
        freshness check."""
        opp = Opportunity(
            id=new_opportunity_id(),
            detected_at=now_utc(),
            strategy="spatial",
            legs=(_make_intent(),),
            expected_net_profit=Decimal("1.00"),
            confidence=0.5,
            valid_for_ms=750,
        )
        assert hasattr(opp, "valid_for_ms")
        assert opp.valid_for_ms == 750


# ---------- RiskDecision ----------

class TestRiskDecision:
    def test_approval_carries_reason(self):
        d = RiskDecision(
            opportunity_id=new_opportunity_id(),
            approved=True,
            reason="all checks passed",
        )
        assert d.approved is True
        assert d.reason == "all checks passed"
        assert d.adjusted_quantity is None

    def test_rejection_carries_reason(self):
        d = RiskDecision(
            opportunity_id=new_opportunity_id(),
            approved=False,
            reason="position_limit_exceeded",
        )
        assert d.approved is False
        assert "position_limit_exceeded" in d.reason

    def test_adjusted_quantity_can_downsize(self):
        d = RiskDecision(
            opportunity_id=new_opportunity_id(),
            approved=True,
            reason="position_limit; downsized",
            adjusted_quantity=volume("0.005"),
        )
        assert d.adjusted_quantity == Decimal("0.005")

    def test_frozen(self):
        d = RiskDecision(
            opportunity_id=new_opportunity_id(),
            approved=True,
            reason="ok",
        )
        with pytest.raises(FrozenInstanceError):
            d.approved = False  # type: ignore[misc]


# ---------- Fill ----------

class TestFill:
    def test_constructs_buy(self):
        f = Fill(
            opportunity_id=new_opportunity_id(),
            exchange=ExchangeId("binance"),
            symbol=Symbol("BTC", "USDT"),
            side="buy",
            price=price("60000.00"),
            volume=volume("0.01"),
            fee=price("0.10"),
            timestamp_utc=now_utc(),
        )
        assert f.side == "buy"

    def test_uses_timestamp_utc_field(self):
        f = Fill(
            opportunity_id=new_opportunity_id(),
            exchange=ExchangeId("bybit"),
            symbol=Symbol("ETH", "USDT"),
            side="sell",
            price=price("3000"),
            volume=volume("1"),
            fee=price("0"),
            timestamp_utc=now_utc(),
        )
        assert hasattr(f, "timestamp_utc")
        assert not hasattr(f, "timestamp")
