"""Reconciler — pure leg classifier."""

from arbitrage_agent.domain import (
    ExchangeId,
    Fill,
    OrderIntent,
    Symbol,
    new_opportunity_id,
    now_utc,
    price,
    volume,
)
from arbitrage_agent.exchanges.errors import (
    InvalidOrder,
    MarketHalted,
    PermanentFailure,
    RateLimited,
    TemporaryFailure,
)
from arbitrage_agent.execution.reconciler import classify_leg


def _intent(qty="0.001") -> OrderIntent:
    return OrderIntent(
        exchange=ExchangeId("paper"), symbol=Symbol("BTC", "USDT"),
        side="buy", quantity=volume(qty), limit_price=price("60000"),
    )


def _fill(qty="0.001") -> Fill:
    return Fill(
        opportunity_id=new_opportunity_id(),
        exchange=ExchangeId("paper"), symbol=Symbol("BTC", "USDT"),
        side="buy", price=price("60000"), volume=volume(qty),
        fee=price("0.06"), timestamp_utc=now_utc(),
    )


# ---- Success paths -------------------------------------------------------


def test_full_quantity_filled():
    assert classify_leg(_intent("1.0"), None, [_fill("1.0")]) == "filled"


def test_excess_qty_still_filled():
    """Exchange filled MORE than asked (rare overfill) → still FILLED."""
    assert classify_leg(_intent("1.0"), None, [_fill("1.1")]) == "filled"


def test_partial_fill():
    assert classify_leg(_intent("1.0"), None, [_fill("0.3")]) == "partial"


def test_split_fills_summed_for_full():
    """Two fills totalling intent.quantity → FILLED."""
    assert (
        classify_leg(_intent("1.0"), None, [_fill("0.4"), _fill("0.6")])
        == "filled"
    )


def test_no_error_no_fill_means_cancelled():
    """Adapter succeeded, no fills observed in the window → CANCELLED."""
    assert classify_leg(_intent("1.0"), None, []) == "cancelled"


# ---- Error mapping -------------------------------------------------------


def test_invalid_order_classifies_as_rejected():
    assert classify_leg(_intent(), InvalidOrder("bad symbol"), []) == "rejected"


def test_market_halted_classifies_as_rejected():
    assert classify_leg(_intent(), MarketHalted("halted"), []) == "rejected"


def test_permanent_failure_classifies_as_rejected():
    assert classify_leg(_intent(), PermanentFailure("ip banned"), []) == "rejected"


def test_rate_limited_classifies_as_failed():
    """Retryable exchange feedback → FAILED (operator + reconciler decide)."""
    assert classify_leg(_intent(), RateLimited("slow down"), []) == "failed"


def test_temporary_failure_classifies_as_failed():
    assert classify_leg(_intent(), TemporaryFailure("net blip"), []) == "failed"


def test_unknown_exception_classifies_as_failed():
    """Conservative default — unknown errors require reconciliation."""
    assert classify_leg(_intent(), RuntimeError("???"), []) == "failed"


def test_error_overrides_fills():
    """If both an error and fills are present, error wins — we don't
    know what the exchange's final state actually is."""
    assert (
        classify_leg(_intent("1.0"), TemporaryFailure("net"), [_fill("1.0")])
        == "failed"
    )
