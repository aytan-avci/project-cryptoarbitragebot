"""Execution engine — concurrent placement + per-leg timeout + reconciler
classification (Faz 7e)."""

import asyncio
from decimal import Decimal

import pytest

from arbitrage_agent.domain import (
    ExchangeId,
    ExecutionResult,
    MarketSnapshot,
    Opportunity,
    OrderIntent,
    RiskDecision,
    Symbol,
    new_opportunity_id,
    now_utc,
    price,
    volume,
)
from arbitrage_agent.exchanges.paper import PaperExchange
from arbitrage_agent.execution.engine import execute


def _seed_paper(name: str) -> PaperExchange:
    return PaperExchange(
        name=name,
        prices={Symbol("BTC", "USDT"): MarketSnapshot(
            exchange=ExchangeId(name), symbol=Symbol("BTC", "USDT"),
            bid=price("60000"), ask=price("60001"),
            bid_size=volume("10"), ask_size=volume("10"),
            timestamp_utc=now_utc(),
        )},
    )


def _opp_two_legs(opp_id=None, valid_for_ms: int = 1000) -> Opportunity:
    a = ExchangeId("binance")
    b = ExchangeId("bybit")
    buy = OrderIntent(exchange=a, symbol=Symbol("BTC", "USDT"),
                     side="buy", quantity=volume("0.001"), limit_price=price("60000"))
    sell = OrderIntent(exchange=b, symbol=Symbol("BTC", "USDT"),
                      side="sell", quantity=volume("0.001"), limit_price=price("60800"))
    return Opportunity(
        id=opp_id or new_opportunity_id(),
        detected_at=now_utc(),
        strategy="spatial",
        legs=(buy, sell),
        expected_net_profit=Decimal("0.5"),
        confidence=0.9,
        valid_for_ms=valid_for_ms,
    )


# ---- Happy path ----------------------------------------------------------


def test_happy_returns_execution_result_with_filled_legs():
    opp = _opp_two_legs()
    decision = RiskDecision(opportunity_id=opp.id, approved=True, reason="ok")
    adapters = {ExchangeId("binance"): _seed_paper("binance"),
                ExchangeId("bybit"): _seed_paper("bybit")}
    result = asyncio.run(execute(opp, decision, adapters))

    assert isinstance(result, ExecutionResult)
    assert result.opportunity_id == opp.id
    assert len(result.legs) == 2
    assert all(lr.state == "filled" for lr in result.legs)
    assert result.all_filled is True
    assert result.needs_hedge is False


def test_legs_run_concurrently():
    """Two adapters with artificial delays — concurrent placement is
    fast (~max(delay)), sequential would be sum(delays)."""
    import time as _time

    class SlowPaper(PaperExchange):
        def __init__(self, name, delay_s):
            super().__init__(
                name=name,
                prices={Symbol("BTC", "USDT"): MarketSnapshot(
                    exchange=ExchangeId(name), symbol=Symbol("BTC", "USDT"),
                    bid=price("60000"), ask=price("60001"),
                    bid_size=volume("10"), ask_size=volume("10"),
                    timestamp_utc=now_utc(),
                )},
            )
            self._delay = delay_s

        async def place_order(self, intent, decision):
            await asyncio.sleep(self._delay)
            return await super().place_order(intent, decision)

    opp = _opp_two_legs(valid_for_ms=2000)
    decision = RiskDecision(opportunity_id=opp.id, approved=True, reason="ok")
    adapters = {ExchangeId("binance"): SlowPaper("binance", 0.2),
                ExchangeId("bybit"): SlowPaper("bybit", 0.2)}

    t0 = _time.monotonic()
    result = asyncio.run(execute(opp, decision, adapters))
    elapsed = _time.monotonic() - t0

    assert all(lr.state == "filled" for lr in result.legs)
    # Sequential would be ~0.4s; concurrent ~0.2s with a margin.
    assert elapsed < 0.35


# ---- Per-leg timeout -----------------------------------------------------


def test_leg_timeout_marks_failed():
    class HangPaper(PaperExchange):
        async def place_order(self, intent, decision):
            await asyncio.sleep(10)  # never within the test window
            return await super().place_order(intent, decision)

    opp = _opp_two_legs(valid_for_ms=200)  # 0.2 s
    decision = RiskDecision(opportunity_id=opp.id, approved=True, reason="ok")
    adapters = {ExchangeId("binance"): HangPaper(name="binance"),
                ExchangeId("bybit"): _seed_paper("bybit")}

    result = asyncio.run(execute(opp, decision, adapters))
    states = [lr.state for lr in result.legs]
    assert "failed" in states  # the hanging leg
    assert "filled" in states  # the fast leg
    assert result.needs_hedge is True


# ---- Adapter error per leg -----------------------------------------------


def test_one_leg_adapter_error_classified():
    from arbitrage_agent.exchanges.errors import InvalidOrder

    class BadPaper(PaperExchange):
        async def place_order(self, intent, decision):
            raise InvalidOrder("simulated rejection")

    opp = _opp_two_legs()
    decision = RiskDecision(opportunity_id=opp.id, approved=True, reason="ok")
    adapters = {ExchangeId("binance"): BadPaper(name="binance"),
                ExchangeId("bybit"): _seed_paper("bybit")}

    result = asyncio.run(execute(opp, decision, adapters))
    states = {lr.leg.exchange: lr.state for lr in result.legs}
    assert states["binance"] == "rejected"
    assert states["bybit"] == "filled"
    # error message captured on the failing leg
    bad_leg = next(lr for lr in result.legs if lr.leg.exchange == "binance")
    assert bad_leg.error_message and "InvalidOrder" in bad_leg.error_message


# ---- Cardinal-rule guards ------------------------------------------------


def test_unapproved_decision_raises():
    opp = _opp_two_legs()
    decision = RiskDecision(opportunity_id=opp.id, approved=False, reason="no")
    adapters = {ExchangeId("binance"): _seed_paper("binance"),
                ExchangeId("bybit"): _seed_paper("bybit")}
    with pytest.raises(ValueError, match="approved decision"):
        asyncio.run(execute(opp, decision, adapters))


def test_mismatched_opportunity_id_raises():
    opp = _opp_two_legs()
    wrong_decision = RiskDecision(
        opportunity_id=new_opportunity_id(),
        approved=True, reason="ok",
    )
    adapters = {ExchangeId("binance"): _seed_paper("binance"),
                ExchangeId("bybit"): _seed_paper("bybit")}
    with pytest.raises(ValueError, match="opportunity_id mismatch"):
        asyncio.run(execute(opp, wrong_decision, adapters))


def test_missing_adapter_raises_keyerror_before_any_submit():
    opp = _opp_two_legs()
    decision = RiskDecision(opportunity_id=opp.id, approved=True, reason="ok")
    adapters = {ExchangeId("binance"): _seed_paper("binance")}  # bybit missing
    with pytest.raises(KeyError):
        asyncio.run(execute(opp, decision, adapters))


def test_fills_attributed_per_leg():
    """Each leg's fills come from its own adapter; cross-attribution
    bug would lump them together."""
    opp = _opp_two_legs()
    decision = RiskDecision(opportunity_id=opp.id, approved=True, reason="ok")
    a = _seed_paper("binance")
    b = _seed_paper("bybit")
    adapters = {ExchangeId("binance"): a, ExchangeId("bybit"): b}
    result = asyncio.run(execute(opp, decision, adapters))

    by_exch = {lr.leg.exchange: lr for lr in result.legs}
    assert len(by_exch["binance"].fills) == 1
    assert by_exch["binance"].fills[0].side == "buy"
    assert by_exch["binance"].fills[0].exchange == "binance"
    assert len(by_exch["bybit"].fills) == 1
    assert by_exch["bybit"].fills[0].side == "sell"
    assert by_exch["bybit"].fills[0].exchange == "bybit"
