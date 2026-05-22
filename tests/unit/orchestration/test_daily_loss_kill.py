"""Faz 7g-a — `_maybe_engage_daily_loss_kill` unit-tests."""

import json
import os
from decimal import Decimal
from pathlib import Path

import pytest

from arbitrage_agent.config import Settings
from arbitrage_agent.domain import (
    ExchangeId,
    Fill,
    Symbol,
    new_opportunity_id,
    now_utc,
    price,
    volume,
)
from arbitrage_agent.orchestration.account_state_tracker import AccountStateTracker
from arbitrage_agent.orchestration.pipeline import _maybe_engage_daily_loss_kill


def _clean_env(monkeypatch):
    for k in list(os.environ):
        if k.startswith(("RISK_", "EXECUTION_", "LOG_", "BINANCE_", "BYBIT_",
                         "SPATIAL_", "PIPELINE_", "INGESTION_", "WS_",
                         "BALANCE_", "LIVE_")):
            monkeypatch.delenv(k, raising=False)


def _losing_fill(loss_usd: str) -> Fill:
    """Construct a fill that contributes -`loss_usd` to daily P&L.
    A buy of 1 unit at price `loss_usd + 0` with 0 fee = -loss_usd."""
    return Fill(
        opportunity_id=new_opportunity_id(),
        exchange=ExchangeId("paper"), symbol=Symbol("BTC", "USDT"),
        side="buy",
        price=price(loss_usd),
        volume=volume("1"),
        fee=price("0"),
        timestamp_utc=now_utc(),
    )


def test_no_loss_no_kill(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    _clean_env(monkeypatch)
    settings = Settings()
    tracker = AccountStateTracker()
    fired = _maybe_engage_daily_loss_kill(tracker, settings)
    assert fired is False
    assert tracker.snapshot(0).kill_switch_engaged is False
    assert not (tmp_path / "logs" / "kill_switch.json").exists()


def test_small_loss_under_cap_no_kill(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    _clean_env(monkeypatch)
    settings = Settings()  # default max_loss_per_day_usd = 50
    tracker = AccountStateTracker()
    tracker.on_fill(_losing_fill("10"))  # P&L = -10, under -50 cap
    assert tracker.daily_pnl_usd == Decimal("-10")
    fired = _maybe_engage_daily_loss_kill(tracker, settings)
    assert fired is False
    assert tracker.snapshot(0).kill_switch_engaged is False


def test_loss_at_threshold_no_kill(monkeypatch, tmp_path):
    """Strict `<` — exactly -cap does NOT trigger."""
    monkeypatch.chdir(tmp_path)
    _clean_env(monkeypatch)
    settings = Settings()
    tracker = AccountStateTracker()
    tracker.on_fill(_losing_fill("50"))  # exactly -50
    assert tracker.daily_pnl_usd == Decimal("-50")
    fired = _maybe_engage_daily_loss_kill(tracker, settings)
    assert fired is False


def test_loss_exceeds_cap_engages_kill(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    _clean_env(monkeypatch)
    settings = Settings()
    tracker = AccountStateTracker()
    # Three -20 = -60, exceeds default -50 cap
    for _ in range(3):
        tracker.on_fill(_losing_fill("20"))
    assert tracker.daily_pnl_usd == Decimal("-60")
    fired = _maybe_engage_daily_loss_kill(tracker, settings)
    assert fired is True
    assert tracker.snapshot(0).kill_switch_engaged is True

    # Durable disk record landed
    kill_file = tmp_path / "logs" / "kill_switch.json"
    assert kill_file.exists()
    body = json.loads(kill_file.read_text())
    assert body["engaged"] is True
    assert "daily_loss_breach" in body["reason"]


def test_idempotent_engage_safe_to_call_repeatedly(monkeypatch, tmp_path):
    """If we breach and the helper fires, calling it again should be
    safe (no exception, no behaviour change)."""
    monkeypatch.chdir(tmp_path)
    _clean_env(monkeypatch)
    settings = Settings()
    tracker = AccountStateTracker()
    tracker.on_fill(_losing_fill("100"))
    _maybe_engage_daily_loss_kill(tracker, settings)
    # Second call still True (we re-detect the breach) but tracker
    # remains engaged; disk file is overwritten with current timestamp.
    fired_again = _maybe_engage_daily_loss_kill(tracker, settings)
    assert fired_again is True
    assert tracker.snapshot(0).kill_switch_engaged is True
