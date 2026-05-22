"""Tests for `risk/gate.evaluate` — the cardinal rule's enforcement point.

Per `skills/risk-management/SKILL.md § Decision Order`, the first failing
check stops the chain. We verify each check rejects in isolation, then
verify the order with a 2-violation scenario.
"""

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from arbitrage_agent.domain import (
    ExchangeId,
    Opportunity,
    OrderIntent,
    Symbol,
    new_opportunity_id,
    price,
    volume,
)
from arbitrage_agent.risk.gate import evaluate
from arbitrage_agent.risk.limits import AccountState, Limits


# ---- Builders --------------------------------------------------------------

def _limits(**overrides) -> Limits:
    base = dict(
        min_profit_threshold_usd=Decimal("0.50"),
        min_order_value_usd=Decimal("20"),
        max_order_value_usd=Decimal("200"),
        max_gross_exposure_usd=Decimal("1500"),
        max_position_value_usd=Decimal("500"),
        max_orders_per_minute=30,
        max_snapshot_age_ms=10_000,
        min_required_balance_usd=Decimal("50"),
        max_loss_per_day_usd=Decimal("50"),
    )
    base.update(overrides)
    return Limits(**base)


def _leg(quantity="0.001", limit_price="60000") -> OrderIntent:
    """Default leg: 0.001 BTC × 60_000 USDT = 60 USD value."""
    return OrderIntent(
        exchange=ExchangeId("paper"),
        symbol=Symbol("BTC", "USDT"),
        side="buy",
        quantity=volume(quantity),
        limit_price=price(limit_price),
    )


def _opp(
    *,
    detected_at: datetime | None = None,
    legs: tuple[OrderIntent, ...] | None = None,
    expected_net_profit: str = "5.00",
    confidence: float = 0.9,
    valid_for_ms: int = 1000,
) -> Opportunity:
    return Opportunity(
        id=new_opportunity_id(),
        detected_at=detected_at or datetime.now(timezone.utc),
        strategy="spatial",
        legs=legs or (_leg(), _leg()),
        expected_net_profit=Decimal(expected_net_profit),
        confidence=confidence,
        valid_for_ms=valid_for_ms,
    )


def _now_ms(dt: datetime) -> int:
    return int(dt.timestamp() * 1000)


# ---- Happy path ------------------------------------------------------------

class TestHappyPath:
    def test_all_checks_pass(self):
        now = datetime.now(timezone.utc)
        opp = _opp(detected_at=now)
        decision = evaluate(opp, AccountState(), _limits(), _now_ms(now))
        assert decision.approved is True
        assert decision.reason == "all checks passed"
        assert decision.opportunity_id == opp.id


# ---- Individual rejection paths --------------------------------------------

class TestKillSwitchCheck:
    def test_engaged_rejects_first(self):
        now = datetime.now(timezone.utc)
        # Build an opportunity that would ALSO fail freshness; the
        # kill-switch reason must win because it's check #1.
        old = now - timedelta(seconds=10)
        opp = _opp(detected_at=old)
        state = AccountState(kill_switch_engaged=True)
        d = evaluate(opp, state, _limits(), _now_ms(now))
        assert d.approved is False
        assert d.reason == "kill_switch_engaged"


class TestFreshnessCheck:
    def test_stale_rejects(self):
        now = datetime.now(timezone.utc)
        stale = now - timedelta(seconds=5)
        opp = _opp(detected_at=stale)
        d = evaluate(opp, AccountState(), _limits(), _now_ms(now))
        assert d.approved is False
        assert d.reason.startswith("stale: age_ms=")

    def test_at_exact_threshold_passes(self):
        now = datetime.now(timezone.utc)
        opp = _opp(detected_at=now - timedelta(milliseconds=1000), valid_for_ms=1000)
        d = evaluate(opp, AccountState(), _limits(), _now_ms(now))
        assert d.approved is True  # age_ms == 1000, NOT > 1000

    def test_strategy_specific_valid_for_ms_honoured(self):
        """Different strategies declare different shelf-lives."""
        now = datetime.now(timezone.utc)
        # 600ms old: passes 1000-ms shelf, fails 500-ms shelf
        old = now - timedelta(milliseconds=600)
        opp_lenient = _opp(detected_at=old, valid_for_ms=1000)
        opp_strict = _opp(detected_at=old, valid_for_ms=500)
        d1 = evaluate(opp_lenient, AccountState(), _limits(), _now_ms(now))
        d2 = evaluate(opp_strict, AccountState(), _limits(), _now_ms(now))
        assert d1.approved is True
        assert d2.approved is False
        assert d2.reason.startswith("stale:")

    def test_future_opportunity_is_fresh(self):
        # Clock-skew defence: negative age treated as fresh, not reject.
        now = datetime.now(timezone.utc)
        future = now + timedelta(milliseconds=500)
        opp = _opp(detected_at=future)
        d = evaluate(opp, AccountState(), _limits(), _now_ms(now))
        assert d.approved is True


class TestProfitabilityCheck:
    def test_below_threshold_rejects(self):
        now = datetime.now(timezone.utc)
        opp = _opp(detected_at=now, expected_net_profit="0.10")  # below 0.50
        d = evaluate(opp, AccountState(), _limits(), _now_ms(now))
        assert d.approved is False
        assert d.reason.startswith("profit_below_threshold")

    def test_at_threshold_passes(self):
        now = datetime.now(timezone.utc)
        opp = _opp(detected_at=now, expected_net_profit="0.50")
        d = evaluate(opp, AccountState(), _limits(), _now_ms(now))
        assert d.approved is True


class TestMinOrderValue:
    def test_dust_leg_rejects(self):
        now = datetime.now(timezone.utc)
        # 0.0001 BTC × 60_000 = 6 USD (below min 20)
        opp = _opp(detected_at=now, legs=(_leg(quantity="0.0001"), _leg()))
        d = evaluate(opp, AccountState(), _limits(), _now_ms(now))
        assert d.approved is False
        assert d.reason.startswith("leg_below_min_order_value")


class TestMaxOrderValue:
    def test_oversized_leg_rejects(self):
        now = datetime.now(timezone.utc)
        # 0.01 BTC × 60_000 = 600 USD (above max 200)
        opp = _opp(detected_at=now, legs=(_leg(quantity="0.01"), _leg()))
        d = evaluate(opp, AccountState(), _limits(), _now_ms(now))
        assert d.approved is False
        assert d.reason.startswith("leg_above_max_order_value")


class TestGrossExposure:
    def test_sum_breach_rejects(self):
        now = datetime.now(timezone.utc)
        # 30 legs × 60 USD = 1800 USD > 1500
        many_legs = tuple(_leg() for _ in range(30))
        opp = _opp(detected_at=now, legs=many_legs)
        d = evaluate(opp, AccountState(), _limits(), _now_ms(now))
        assert d.approved is False
        assert d.reason.startswith("gross_exposure_breach")


# ---- Decision-order regression ---------------------------------------------

class TestDecisionOrder:
    def test_kill_switch_beats_freshness(self):
        # Already covered above, but explicit ordering test
        now = datetime.now(timezone.utc)
        opp = _opp(detected_at=now - timedelta(seconds=10))
        state = AccountState(kill_switch_engaged=True)
        d = evaluate(opp, state, _limits(), _now_ms(now))
        assert d.reason == "kill_switch_engaged"

    def test_freshness_beats_profitability(self):
        now = datetime.now(timezone.utc)
        opp = _opp(
            detected_at=now - timedelta(seconds=10),
            expected_net_profit="0.01",  # also below threshold
        )
        d = evaluate(opp, AccountState(), _limits(), _now_ms(now))
        assert d.reason.startswith("stale:")

    def test_profitability_beats_order_value(self):
        now = datetime.now(timezone.utc)
        opp = _opp(
            detected_at=now,
            expected_net_profit="0.01",
            legs=(_leg(quantity="0.0001"),),  # also below min order value
        )
        d = evaluate(opp, AccountState(), _limits(), _now_ms(now))
        assert d.reason.startswith("profit_below_threshold")


# ---- Opportunity_id traceability -------------------------------------------

class TestTraceability:
    def test_rejection_carries_opportunity_id(self):
        now = datetime.now(timezone.utc)
        opp = _opp(detected_at=now, expected_net_profit="0.01")
        d = evaluate(opp, AccountState(), _limits(), _now_ms(now))
        assert d.opportunity_id == opp.id

    def test_approval_carries_opportunity_id(self):
        now = datetime.now(timezone.utc)
        opp = _opp(detected_at=now)
        d = evaluate(opp, AccountState(), _limits(), _now_ms(now))
        assert d.opportunity_id == opp.id


# ---- Faz 7f checks --------------------------------------------------------


class TestPositionLimit:
    def test_buy_at_or_below_cap_passes(self):
        now = datetime.now(timezone.utc)
        # leg: 0.001 BTC × 60_000 = 60 USD; cap default 500 — well under
        opp = _opp(detected_at=now)
        d = evaluate(opp, AccountState(), _limits(), _now_ms(now))
        assert d.approved is True

    def test_buy_breaches_cap_rejects(self):
        now = datetime.now(timezone.utc)
        # Current pos 0.008 BTC × 60_000 = 480; adding 0.001 takes us to
        # 0.009 × 60_000 = 540 > 500 cap
        state = AccountState(
            open_position_qty={
                (ExchangeId("paper"), Symbol("BTC", "USDT")): volume("0.008"),
            }
        )
        opp = _opp(detected_at=now)
        d = evaluate(opp, state, _limits(), _now_ms(now))
        assert d.approved is False
        assert d.reason.startswith("position_limit:")

    def test_sell_reduces_absolute_position(self):
        """If we are LONG 0.008 BTC and SELL 0.001, abs goes 0.008 → 0.007,
        still under 500 USD cap. Approved."""
        now = datetime.now(timezone.utc)
        state = AccountState(
            open_position_qty={
                (ExchangeId("paper"), Symbol("BTC", "USDT")): volume("0.008"),
            }
        )
        # Override the default _leg to be a sell
        sell_leg = OrderIntent(
            exchange=ExchangeId("paper"), symbol=Symbol("BTC", "USDT"),
            side="sell", quantity=volume("0.001"), limit_price=price("60000"),
        )
        opp = _opp(detected_at=now, legs=(sell_leg, sell_leg))
        d = evaluate(opp, state, _limits(), _now_ms(now))
        assert d.approved is True


class TestOrdersPerMinute:
    def test_under_limit_passes(self):
        now = datetime.now(timezone.utc)
        now_ms = _now_ms(now)
        state = AccountState(
            recent_order_timestamps_ms=tuple(now_ms - i * 1000 for i in range(20)),
        )
        opp = _opp(detected_at=now)  # 2 legs
        # 20 recent + 2 new = 22, under 30 cap
        d = evaluate(opp, state, _limits(), now_ms)
        assert d.approved is True

    def test_at_or_above_cap_rejects(self):
        now = datetime.now(timezone.utc)
        now_ms = _now_ms(now)
        # 29 recent + 2 new = 31, > 30 cap → reject
        state = AccountState(
            recent_order_timestamps_ms=tuple(now_ms - i * 1000 for i in range(29)),
        )
        opp = _opp(detected_at=now)
        d = evaluate(opp, state, _limits(), now_ms)
        assert d.approved is False
        assert d.reason.startswith("orders_per_minute:")

    def test_old_timestamps_outside_window_ignored(self):
        now = datetime.now(timezone.utc)
        now_ms = _now_ms(now)
        # 100 timestamps from > 60 s ago — all outside window
        state = AccountState(
            recent_order_timestamps_ms=tuple(
                now_ms - 70_000 - i for i in range(100)
            ),
        )
        opp = _opp(detected_at=now)
        d = evaluate(opp, state, _limits(), now_ms)
        assert d.approved is True


class TestVenueFreshness:
    def test_fresh_venue_passes(self):
        now = datetime.now(timezone.utc)
        state = AccountState(
            last_snapshot_age_ms_by_venue={ExchangeId("paper"): 500},
        )
        opp = _opp(detected_at=now)
        d = evaluate(opp, state, _limits(), _now_ms(now))
        assert d.approved is True

    def test_stale_venue_rejects(self):
        now = datetime.now(timezone.utc)
        state = AccountState(
            last_snapshot_age_ms_by_venue={ExchangeId("paper"): 15_000},
        )
        opp = _opp(detected_at=now)
        d = evaluate(opp, state, _limits(), _now_ms(now))
        assert d.approved is False
        assert d.reason.startswith("venue_stale:")

    def test_unknown_venue_skips_check(self):
        """If freshness for a leg's venue is not tracked, the check is
        skipped (rather than failing closed). Allows pre-Faz-7f tests
        and integration smoke runs to keep working."""
        now = datetime.now(timezone.utc)
        state = AccountState(
            last_snapshot_age_ms_by_venue={},  # no entries
        )
        opp = _opp(detected_at=now)
        d = evaluate(opp, state, _limits(), _now_ms(now))
        assert d.approved is True


class TestMinRequiredBalance:
    """Faz 7g-a — check 10. Same absent-=-skip semantics as freshness."""

    def test_unknown_balance_skips_check(self):
        now = datetime.now(timezone.utc)
        state = AccountState(cash_by_exchange={})
        opp = _opp(detected_at=now)
        d = evaluate(opp, state, _limits(), _now_ms(now))
        assert d.approved is True

    def test_balance_above_threshold_passes(self):
        now = datetime.now(timezone.utc)
        state = AccountState(
            cash_by_exchange={ExchangeId("paper"): Decimal("1000")},
        )
        opp = _opp(detected_at=now)
        d = evaluate(opp, state, _limits(), _now_ms(now))
        assert d.approved is True

    def test_balance_below_threshold_rejects(self):
        now = datetime.now(timezone.utc)
        state = AccountState(
            cash_by_exchange={ExchangeId("paper"): Decimal("25")},
        )
        opp = _opp(detected_at=now)
        d = evaluate(opp, state, _limits(), _now_ms(now))
        assert d.approved is False
        assert d.reason.startswith("min_balance:")

    def test_balance_at_threshold_passes(self):
        """Strict `<` — exact-threshold cash should NOT trigger reject."""
        now = datetime.now(timezone.utc)
        state = AccountState(
            cash_by_exchange={ExchangeId("paper"): Decimal("50")},
        )
        opp = _opp(detected_at=now)
        d = evaluate(opp, state, _limits(), _now_ms(now))
        assert d.approved is True


class TestFaz7fOrdering:
    def test_position_check_runs_after_gross_exposure(self):
        """Decision order: gross_exposure (check 6) before position
        (check 7). Two violations present → first one (gross) wins."""
        now = datetime.now(timezone.utc)
        # 30 legs × $60 = $1800 → gross exposure breach
        many_legs = tuple(_leg() for _ in range(30))
        state = AccountState(
            open_position_qty={
                (ExchangeId("paper"), Symbol("BTC", "USDT")): volume("0.008"),
            }
        )
        opp = _opp(detected_at=now, legs=many_legs)
        d = evaluate(opp, state, _limits(), _now_ms(now))
        assert d.reason.startswith("gross_exposure_breach:")

    def test_position_check_runs_before_orders_per_min(self):
        now = datetime.now(timezone.utc)
        now_ms = _now_ms(now)
        state = AccountState(
            open_position_qty={
                (ExchangeId("paper"), Symbol("BTC", "USDT")): volume("0.008"),
            },
            recent_order_timestamps_ms=tuple(now_ms for _ in range(40)),
        )
        opp = _opp(detected_at=now)
        d = evaluate(opp, state, _limits(), now_ms)
        assert d.reason.startswith("position_limit:")
