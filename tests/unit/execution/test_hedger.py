"""Execution hedger — net exposure, slippage budget, counter-leg
placement (Faz 7g-c)."""

import asyncio
from decimal import Decimal

import pytest

from arbitrage_agent.domain import (
    ExchangeId,
    ExecutionResult,
    Fill,
    LegResult,
    MarketSnapshot,
    Opportunity,
    OpportunityId,
    OrderId,
    OrderIntent,
    RiskDecision,
    Symbol,
    new_opportunity_id,
    now_utc,
    price,
    volume,
)
from arbitrage_agent.exchanges.paper import PaperExchange
from arbitrage_agent.execution.hedger import (
    _within_slippage,
    compute_net_exposure,
    hedge,
)
from arbitrage_agent.ingestion.bus import LatestSnapshotView


_BTC = Symbol("BTC", "USDT")
_BINANCE = ExchangeId("binance")
_BYBIT = ExchangeId("bybit")


def _opp() -> Opportunity:
    buy = OrderIntent(exchange=_BINANCE, symbol=_BTC, side="buy",
                     quantity=volume("0.001"), limit_price=price("60000"))
    sell = OrderIntent(exchange=_BYBIT, symbol=_BTC, side="sell",
                      quantity=volume("0.001"), limit_price=price("60800"))
    return Opportunity(
        id=new_opportunity_id(),
        detected_at=now_utc(),
        strategy="spatial",
        legs=(buy, sell),
        expected_net_profit=Decimal("0.5"),
        confidence=0.9,
        valid_for_ms=1000,
    )


def _fill(opp_id: OpportunityId, exchange: ExchangeId, side: str,
          qty: str, px: str) -> Fill:
    return Fill(
        opportunity_id=opp_id,
        exchange=exchange,
        symbol=_BTC,
        side=side,
        price=price(px),
        volume=volume(qty),
        fee=price("0"),
        timestamp_utc=now_utc(),
    )


def _seed_view(bid: str, ask: str, exchange: ExchangeId = _BYBIT) -> LatestSnapshotView:
    view = LatestSnapshotView()
    view.update(MarketSnapshot(
        exchange=exchange, symbol=_BTC,
        bid=price(bid), ask=price(ask),
        bid_size=volume("10"), ask_size=volume("10"),
        timestamp_utc=now_utc(),
    ))
    return view


def _adapters_two_paper(bid_a="60000", ask_a="60001",
                       bid_b="60800", ask_b="60801") -> dict[ExchangeId, PaperExchange]:
    return {
        _BINANCE: PaperExchange(
            name="binance",
            prices={_BTC: MarketSnapshot(
                exchange=_BINANCE, symbol=_BTC,
                bid=price(bid_a), ask=price(ask_a),
                bid_size=volume("10"), ask_size=volume("10"),
                timestamp_utc=now_utc(),
            )},
        ),
        _BYBIT: PaperExchange(
            name="bybit",
            prices={_BTC: MarketSnapshot(
                exchange=_BYBIT, symbol=_BTC,
                bid=price(bid_b), ask=price(ask_b),
                bid_size=volume("10"), ask_size=volume("10"),
                timestamp_utc=now_utc(),
            )},
        ),
    }


# ---- compute_net_exposure -------------------------------------------------


def test_net_exposure_zero_when_all_legs_balanced():
    opp = _opp()
    result = ExecutionResult(
        opportunity_id=opp.id,
        legs=(
            LegResult(leg=opp.legs[0], order_id=OrderId("a"), state="filled",
                      fills=(_fill(opp.id, _BINANCE, "buy", "0.001", "60000"),)),
            LegResult(leg=opp.legs[1], order_id=OrderId("b"), state="filled",
                      fills=(_fill(opp.id, _BYBIT, "sell", "0.001", "60800"),)),
        ),
    )
    assert compute_net_exposure(result) == {}


def test_net_exposure_long_when_sell_leg_unfilled():
    opp = _opp()
    result = ExecutionResult(
        opportunity_id=opp.id,
        legs=(
            LegResult(leg=opp.legs[0], order_id=OrderId("a"), state="filled",
                      fills=(_fill(opp.id, _BINANCE, "buy", "0.001", "60000"),)),
            LegResult(leg=opp.legs[1], order_id=None, state="failed",
                      fills=()),
        ),
    )
    nets = compute_net_exposure(result)
    assert nets == {_BTC: Decimal("0.001")}


def test_net_exposure_partial_legs_aggregate_signed():
    """Buy leg fills 0.001, sell leg fills 0.0004 → net +0.0006."""
    opp = _opp()
    result = ExecutionResult(
        opportunity_id=opp.id,
        legs=(
            LegResult(leg=opp.legs[0], order_id=OrderId("a"), state="filled",
                      fills=(_fill(opp.id, _BINANCE, "buy", "0.001", "60000"),)),
            LegResult(leg=opp.legs[1], order_id=OrderId("b"), state="partial",
                      fills=(_fill(opp.id, _BYBIT, "sell", "0.0004", "60800"),)),
        ),
    )
    nets = compute_net_exposure(result)
    assert nets[_BTC] == Decimal("0.0006")


# ---- slippage gate (pure) -------------------------------------------------


def test_slippage_sell_within_budget():
    # Bought avg 60000; selling at 59700 = 50bps drift = exactly budget.
    assert _within_slippage(Decimal("60000"), Decimal("59700"), "sell", 50) is True


def test_slippage_sell_beyond_budget():
    # Selling at 59500 = 83bps drift; 50bps budget rejects.
    assert _within_slippage(Decimal("60000"), Decimal("59500"), "sell", 50) is False


def test_slippage_buy_beyond_budget():
    # Sold avg 60800; buying back at 61500 = 115bps drift.
    assert _within_slippage(Decimal("60800"), Decimal("61500"), "buy", 50) is False


# ---- hedge orchestration --------------------------------------------------


def test_hedge_no_imbalance_returns_early():
    opp = _opp()
    result = ExecutionResult(
        opportunity_id=opp.id,
        legs=(
            LegResult(leg=opp.legs[0], order_id=OrderId("a"), state="filled",
                      fills=(_fill(opp.id, _BINANCE, "buy", "0.001", "60000"),)),
            LegResult(leg=opp.legs[1], order_id=OrderId("b"), state="filled",
                      fills=(_fill(opp.id, _BYBIT, "sell", "0.001", "60800"),)),
        ),
    )
    out = asyncio.run(hedge(opp, result, _adapters_two_paper(),
                            _seed_view("60800", "60801"), max_slippage_bps=50))
    assert out.status == "no_imbalance"
    assert out.counter_leg is None
    assert out.remaining_exposure == 0


def test_hedge_places_counter_leg_when_sell_leg_failed():
    """Buy filled on Binance, sell failed on Bybit → counter-leg sells
    0.001 BTC on Bybit. Bybit's snapshot has tight spread (60800/60801),
    so slippage stays within budget."""
    opp = _opp()
    result = ExecutionResult(
        opportunity_id=opp.id,
        legs=(
            LegResult(leg=opp.legs[0], order_id=OrderId("a"), state="filled",
                      fills=(_fill(opp.id, _BINANCE, "buy", "0.001", "60000"),)),
            LegResult(leg=opp.legs[1], order_id=None, state="failed", fills=()),
        ),
    )
    adapters = _adapters_two_paper()
    out = asyncio.run(hedge(
        opp, result, adapters,
        _seed_view("60800", "60801", exchange=_BYBIT),
        max_slippage_bps=10_000,  # generous — happy path test
    ))
    assert out.status == "filled"
    assert out.counter_leg is not None
    assert out.counter_leg.side == "sell"
    assert out.counter_leg.exchange == _BYBIT
    assert out.counter_leg.quantity == Decimal("0.001")
    assert out.remaining_exposure == 0
    assert len(out.fills) == 1
    assert out.fills[0].side == "sell"


def test_hedge_aborts_when_slippage_exceeds_budget():
    """Bought at 60000; Bybit best bid is 59000 → 167bps drift, 50bps
    budget rejects. No order placed, status = aborted_slippage,
    remaining_exposure carries the position for the operator."""
    opp = _opp()
    result = ExecutionResult(
        opportunity_id=opp.id,
        legs=(
            LegResult(leg=opp.legs[0], order_id=OrderId("a"), state="filled",
                      fills=(_fill(opp.id, _BINANCE, "buy", "0.001", "60000"),)),
            LegResult(leg=opp.legs[1], order_id=None, state="failed", fills=()),
        ),
    )
    # Bybit bid crashed from 60800 expected → 59000 actual.
    adapters = _adapters_two_paper(bid_b="59000", ask_b="59001")
    out = asyncio.run(hedge(
        opp, result, adapters,
        _seed_view("59000", "59001", exchange=_BYBIT),
        max_slippage_bps=50,
    ))
    assert out.status == "aborted_slippage"
    assert out.counter_leg is None
    assert out.remaining_exposure == Decimal("0.001")
    # No fills on Bybit means nothing was placed.
    assert asyncio.run(adapters[_BYBIT].fetch_fills(since=opp.detected_at)) == []


def test_hedge_no_market_data_when_view_empty():
    opp = _opp()
    result = ExecutionResult(
        opportunity_id=opp.id,
        legs=(
            LegResult(leg=opp.legs[0], order_id=OrderId("a"), state="filled",
                      fills=(_fill(opp.id, _BINANCE, "buy", "0.001", "60000"),)),
            LegResult(leg=opp.legs[1], order_id=None, state="failed", fills=()),
        ),
    )
    out = asyncio.run(hedge(
        opp, result, _adapters_two_paper(), LatestSnapshotView(),
        max_slippage_bps=50,
    ))
    assert out.status == "no_market_data"
    assert out.remaining_exposure == Decimal("0.001")


def test_hedge_swallows_cancel_failure_but_still_places_counter():
    """A partial leg whose cancel_order raises must NOT block the
    hedger from placing the counter-leg. The cancel is best-effort."""

    class CancelExploder(PaperExchange):
        async def cancel_order(self, order_id):
            raise RuntimeError("venue rejected cancel")

    opp = _opp()
    result = ExecutionResult(
        opportunity_id=opp.id,
        legs=(
            LegResult(leg=opp.legs[0], order_id=OrderId("a"), state="filled",
                      fills=(_fill(opp.id, _BINANCE, "buy", "0.001", "60000"),)),
            LegResult(leg=opp.legs[1], order_id=OrderId("b"), state="partial",
                      fills=()),  # partial-with-zero-fills is unusual but defensive
        ),
    )
    bybit = CancelExploder(
        name="bybit",
        prices={_BTC: MarketSnapshot(
            exchange=_BYBIT, symbol=_BTC,
            bid=price("60800"), ask=price("60801"),
            bid_size=volume("10"), ask_size=volume("10"),
            timestamp_utc=now_utc(),
        )},
    )
    adapters = {_BINANCE: _adapters_two_paper()[_BINANCE], _BYBIT: bybit}
    out = asyncio.run(hedge(
        opp, result, adapters,
        _seed_view("60800", "60801", exchange=_BYBIT),
        max_slippage_bps=10_000,
    ))
    assert out.status == "filled"
    assert out.remaining_exposure == 0


def test_hedge_placement_failure_returns_remaining_exposure():
    """Adapter raises on place_order → status=placement_failed and the
    operator sees the open exposure."""

    class PlaceExploder(PaperExchange):
        async def place_order(self, intent, decision):
            raise RuntimeError("exchange rejected order")

    opp = _opp()
    result = ExecutionResult(
        opportunity_id=opp.id,
        legs=(
            LegResult(leg=opp.legs[0], order_id=OrderId("a"), state="filled",
                      fills=(_fill(opp.id, _BINANCE, "buy", "0.001", "60000"),)),
            LegResult(leg=opp.legs[1], order_id=None, state="failed", fills=()),
        ),
    )
    bybit = PlaceExploder(
        name="bybit",
        prices={_BTC: MarketSnapshot(
            exchange=_BYBIT, symbol=_BTC,
            bid=price("60800"), ask=price("60801"),
            bid_size=volume("10"), ask_size=volume("10"),
            timestamp_utc=now_utc(),
        )},
    )
    adapters = {_BINANCE: _adapters_two_paper()[_BINANCE], _BYBIT: bybit}
    out = asyncio.run(hedge(
        opp, result, adapters,
        _seed_view("60800", "60801", exchange=_BYBIT),
        max_slippage_bps=10_000,
    ))
    assert out.status == "placement_failed"
    assert out.remaining_exposure == Decimal("0.001")
    assert "exchange rejected order" in out.reason


def test_hedge_decision_carries_opportunity_id_for_traceability():
    """SKILL.md: 'hedger is the only code that may place an order
    without an upstream Opportunity. The order it places carries a
    special RiskDecision with reason="hedge for opportunity X" and the
    original opportunity_id for traceability.' We assert that the
    counter-leg fills are tagged with the original opportunity_id."""
    opp = _opp()
    result = ExecutionResult(
        opportunity_id=opp.id,
        legs=(
            LegResult(leg=opp.legs[0], order_id=OrderId("a"), state="filled",
                      fills=(_fill(opp.id, _BINANCE, "buy", "0.001", "60000"),)),
            LegResult(leg=opp.legs[1], order_id=None, state="failed", fills=()),
        ),
    )
    adapters = _adapters_two_paper()
    out = asyncio.run(hedge(
        opp, result, adapters,
        _seed_view("60800", "60801", exchange=_BYBIT),
        max_slippage_bps=10_000,
    ))
    assert out.status == "filled"
    assert all(f.opportunity_id == opp.id for f in out.fills)
