"""Tests for `risk/limits.py` — Limits dataclass + Settings projection."""

from dataclasses import FrozenInstanceError
from decimal import Decimal
from pathlib import Path

import pytest

from arbitrage_agent.config import Settings
from arbitrage_agent.risk.limits import AccountState, Limits, limits_from_settings


def _settings(monkeypatch, tmp_path, **overrides) -> Settings:
    monkeypatch.chdir(tmp_path)
    for name in (
        "EXECUTION_MODE",
        "LOG_LEVEL",
        "RISK_MIN_PROFIT_THRESHOLD_USD",
        "RISK_MIN_ORDER_VALUE_USD",
        "RISK_MAX_ORDER_VALUE_USD",
        "RISK_MAX_GROSS_EXPOSURE_USD",
        "RISK_KILL_SWITCH_PATH",
    ):
        monkeypatch.delenv(name, raising=False)
    for k, v in overrides.items():
        monkeypatch.setenv(k, v)
    return Settings()


class TestAccountState:
    def test_default_construction(self):
        s = AccountState()
        assert s.cash_by_exchange == {}
        assert s.open_position_qty == {}
        assert s.kill_switch_engaged is False

    def test_frozen(self):
        s = AccountState()
        with pytest.raises(FrozenInstanceError):
            s.kill_switch_engaged = True  # type: ignore[misc]

    def test_kill_switch_field_carries_state(self):
        s = AccountState(kill_switch_engaged=True)
        assert s.kill_switch_engaged is True


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


class TestLimits:
    def test_constructs(self):
        l = _limits()
        assert l.min_profit_threshold_usd == Decimal("0.50")
        assert l.max_position_value_usd == Decimal("500")
        assert l.max_orders_per_minute == 30
        assert l.max_snapshot_age_ms == 10_000

    def test_frozen(self):
        l = _limits()
        with pytest.raises(FrozenInstanceError):
            l.min_profit_threshold_usd = Decimal("0")  # type: ignore[misc]

    def test_no_max_opportunity_age_field(self):
        """Regression guard: freshness moved to `opportunity.valid_for_ms`
        per SKILL.md § Decision Order. Limits must NOT carry a global cap."""
        l = _limits()
        assert not hasattr(l, "max_opportunity_age_ms")


class TestLimitsFromSettings:
    def test_defaults(self, monkeypatch, tmp_path):
        s = _settings(monkeypatch, tmp_path)
        l = limits_from_settings(s)
        assert l.min_profit_threshold_usd == Decimal("0.50")
        assert l.min_order_value_usd == Decimal("20")
        assert l.max_order_value_usd == Decimal("200")
        assert l.max_gross_exposure_usd == Decimal("1500")
        # Faz 7f defaults
        assert l.max_position_value_usd == Decimal("500")
        assert l.max_orders_per_minute == 30
        assert l.max_snapshot_age_ms == 10_000
        # Faz 7g-a defaults
        assert l.min_required_balance_usd == Decimal("50")
        assert l.max_loss_per_day_usd == Decimal("50")

    def test_env_override(self, monkeypatch, tmp_path):
        s = _settings(
            monkeypatch,
            tmp_path,
            RISK_MAX_GROSS_EXPOSURE_USD="9999.99",
        )
        l = limits_from_settings(s)
        assert l.max_gross_exposure_usd == Decimal("9999.99")

    def test_kill_switch_path_is_path_type(self, monkeypatch, tmp_path):
        s = _settings(monkeypatch, tmp_path)
        assert isinstance(s.risk_kill_switch_path, Path)
        assert s.risk_kill_switch_path.name == "kill_switch.json"
