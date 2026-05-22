"""SECURITY.md S3 — `requires_live_mode` decorator at adapter boundary."""

import pytest

from arbitrage_agent.domain import (
    ExchangeId,
    OrderIntent,
    RiskDecision,
    Symbol,
    new_opportunity_id,
    price,
    volume,
)
from arbitrage_agent.exchanges.base import requires_live_mode
from arbitrage_agent.exchanges.binance import BinanceAdapter


BTC = Symbol("BTC", "USDT")


def _intent_and_decision():
    intent = OrderIntent(
        exchange=ExchangeId("binance"), symbol=BTC, side="buy",
        quantity=volume("0.001"), limit_price=price("60000"),
    )
    decision = RiskDecision(
        opportunity_id=new_opportunity_id(), approved=True, reason="ok",
    )
    return intent, decision


# ---- Decorator unit tests --------------------------------------------------

@pytest.mark.asyncio
async def test_blocks_when_mode_paper(monkeypatch):
    monkeypatch.setenv("EXECUTION_MODE", "paper")

    class Fake:
        @requires_live_mode
        async def do(self):
            return "ran"

    with pytest.raises(PermissionError, match="EXECUTION_MODE='live'"):
        await Fake().do()


@pytest.mark.asyncio
async def test_blocks_when_mode_unset(monkeypatch):
    monkeypatch.delenv("EXECUTION_MODE", raising=False)

    class Fake:
        @requires_live_mode
        async def do(self):
            return "ran"

    with pytest.raises(PermissionError):
        await Fake().do()


@pytest.mark.asyncio
async def test_passes_when_mode_live(monkeypatch):
    monkeypatch.setenv("EXECUTION_MODE", "live")

    class Fake:
        @requires_live_mode
        async def do(self):
            return "ran"

    assert await Fake().do() == "ran"


@pytest.mark.asyncio
async def test_case_insensitive(monkeypatch):
    monkeypatch.setenv("EXECUTION_MODE", "LIVE")

    class Fake:
        @requires_live_mode
        async def do(self):
            return "ran"

    assert await Fake().do() == "ran"


# ---- BinanceAdapter integration -------------------------------------------

@pytest.mark.asyncio
async def test_binance_place_order_blocked_in_paper_mode(monkeypatch):
    """Paper mode: place_order raises PermissionError BEFORE
    NotImplementedError fires (S3 is the first gate)."""
    monkeypatch.setenv("EXECUTION_MODE", "paper")
    adapter = BinanceAdapter()
    intent, decision = _intent_and_decision()
    with pytest.raises(PermissionError):
        await adapter.place_order(intent, decision)


@pytest.mark.asyncio
async def test_binance_place_order_no_credentials_in_live_mode(monkeypatch):
    """Live mode passes S3 → place_order body runs → missing API key
    raises InvalidOrder. Confirms the S3 decorator does NOT short-circuit
    the body when credentials are absent (the body's own check is what
    rejects, not S3)."""
    monkeypatch.setenv("EXECUTION_MODE", "live")
    monkeypatch.setenv("LIVE_TRADING_CONFIRMED", "true")
    from arbitrage_agent.exchanges.errors import InvalidOrder
    adapter = BinanceAdapter()  # no api_key/api_secret
    intent, decision = _intent_and_decision()
    with pytest.raises(InvalidOrder, match="BINANCE_API_KEY"):
        await adapter.place_order(intent, decision)


@pytest.mark.asyncio
async def test_binance_fetch_balance_guarded(monkeypatch):
    monkeypatch.setenv("EXECUTION_MODE", "paper")
    from arbitrage_agent.domain import Asset
    adapter = BinanceAdapter()
    with pytest.raises(PermissionError):
        await adapter.fetch_balance(Asset("USDT"))


@pytest.mark.asyncio
async def test_binance_cancel_order_guarded(monkeypatch):
    monkeypatch.setenv("EXECUTION_MODE", "paper")
    from arbitrage_agent.domain import OrderId
    adapter = BinanceAdapter()
    with pytest.raises(PermissionError):
        await adapter.cancel_order(OrderId("dummy"))


@pytest.mark.asyncio
async def test_binance_fetch_fills_guarded(monkeypatch):
    monkeypatch.setenv("EXECUTION_MODE", "paper")
    from arbitrage_agent.domain import now_utc
    adapter = BinanceAdapter()
    with pytest.raises(PermissionError):
        await adapter.fetch_fills(since=now_utc())
