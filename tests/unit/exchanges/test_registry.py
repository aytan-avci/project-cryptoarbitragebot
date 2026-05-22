"""Registry — Settings → live adapter map."""

import os

import pytest

from arbitrage_agent.config import Settings
from arbitrage_agent.domain import ExchangeId
from arbitrage_agent.exchanges.binance import BinanceAdapter
from arbitrage_agent.exchanges.registry import build_live_adapters


def _clean_env(monkeypatch):
    for k in list(os.environ):
        if k.startswith(
            ("RISK_", "EXECUTION_", "LOG_", "BINANCE_", "BYBIT_",
             "SPATIAL_", "PIPELINE_", "LIVE_TRADING_")
        ):
            monkeypatch.delenv(k, raising=False)


def test_empty_when_no_exchange_enabled(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    _clean_env(monkeypatch)
    adapters = build_live_adapters(Settings())
    assert adapters == {}


def test_includes_binance_when_enabled(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    _clean_env(monkeypatch)
    monkeypatch.setenv("BINANCE_ENABLED", "true")
    adapters = build_live_adapters(Settings())
    assert ExchangeId("binance") in adapters
    assert isinstance(adapters[ExchangeId("binance")], BinanceAdapter)


def test_passes_through_base_url_and_rate_limit(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    _clean_env(monkeypatch)
    monkeypatch.setenv("BINANCE_ENABLED", "true")
    monkeypatch.setenv("BINANCE_REST_BASE_URL", "https://testnet.binance.vision")
    monkeypatch.setenv("BINANCE_RATE_LIMIT_PER_MIN", "30")
    adapters = build_live_adapters(Settings())
    adapter = adapters[ExchangeId("binance")]
    assert isinstance(adapter, BinanceAdapter)
    # Internal fields aren't part of the public protocol; we verify
    # constructor wiring by checking the saved base_url is used.
    assert "testnet.binance.vision" in adapter._base_url  # type: ignore[attr-defined]


def test_includes_bybit_when_enabled(monkeypatch, tmp_path):
    """Faz 7d — Bybit branch in the registry."""
    from arbitrage_agent.exchanges.bybit import BybitAdapter

    monkeypatch.chdir(tmp_path)
    _clean_env(monkeypatch)
    monkeypatch.setenv("BYBIT_ENABLED", "true")
    adapters = build_live_adapters(Settings())
    assert ExchangeId("bybit") in adapters
    assert isinstance(adapters[ExchangeId("bybit")], BybitAdapter)


def test_both_venues_enabled_yields_two_adapters(monkeypatch, tmp_path):
    from arbitrage_agent.exchanges.bybit import BybitAdapter

    monkeypatch.chdir(tmp_path)
    _clean_env(monkeypatch)
    monkeypatch.setenv("BINANCE_ENABLED", "true")
    monkeypatch.setenv("BYBIT_ENABLED", "true")
    # mainnet + live combo would fail S4; keep paper mode here
    adapters = build_live_adapters(Settings())
    assert ExchangeId("binance") in adapters
    assert ExchangeId("bybit") in adapters
    assert isinstance(adapters[ExchangeId("binance")], BinanceAdapter)
    assert isinstance(adapters[ExchangeId("bybit")], BybitAdapter)
