"""Prometheus metrics module — counters, gauges, HTTP exposition (Faz D)."""

import asyncio

import aiohttp
import pytest

from arbitrage_agent.observability import metrics


@pytest.fixture(autouse=True)
def _reset_metrics():
    """Clear labelled metrics + reset gauges between tests so state
    doesn't leak across cases."""
    metrics.clear_for_tests()
    yield
    metrics.clear_for_tests()


def _sample(name: str, **labels) -> float | None:
    """Read the current value of a metric sample via the registry's
    `get_sample_value` helper. Returns None if the labelled child
    doesn't exist yet (counter never incremented)."""
    return metrics.REGISTRY.get_sample_value(name, labels)


# ---- Counters -------------------------------------------------------------


def test_opportunities_counter_increments_per_strategy():
    metrics.opportunities_total.labels(strategy="spatial").inc()
    metrics.opportunities_total.labels(strategy="spatial").inc()
    metrics.opportunities_total.labels(strategy="triangular").inc()
    assert _sample("arbitrage_opportunities_total", strategy="spatial") == 2
    assert _sample("arbitrage_opportunities_total", strategy="triangular") == 1


def test_decisions_counter_separates_approved_and_rejected():
    metrics.decisions_total.labels(outcome="approved").inc()
    metrics.decisions_total.labels(outcome="rejected").inc()
    metrics.decisions_total.labels(outcome="rejected").inc()
    assert _sample("arbitrage_decisions_total", outcome="approved") == 1
    assert _sample("arbitrage_decisions_total", outcome="rejected") == 2


def test_fills_counter_labelled_by_exchange_and_side():
    metrics.fills_total.labels(exchange="binance", side="buy").inc()
    metrics.fills_total.labels(exchange="bybit", side="sell").inc()
    assert _sample("arbitrage_fills_total", exchange="binance", side="buy") == 1
    assert _sample("arbitrage_fills_total", exchange="bybit", side="sell") == 1
    assert _sample("arbitrage_fills_total", exchange="binance", side="sell") is None


def test_hedge_results_counter_separates_statuses():
    metrics.hedge_results_total.labels(status="filled").inc()
    metrics.hedge_results_total.labels(status="aborted_slippage").inc()
    metrics.hedge_results_total.labels(status="filled").inc()
    assert _sample("arbitrage_hedge_results_total", status="filled") == 2
    assert _sample("arbitrage_hedge_results_total", status="aborted_slippage") == 1


# ---- Gauges ---------------------------------------------------------------


def test_kill_switch_gauge_toggles():
    assert _sample("arbitrage_kill_switch_engaged") == 0
    metrics.kill_switch_engaged.set(1)
    assert _sample("arbitrage_kill_switch_engaged") == 1
    metrics.kill_switch_engaged.set(0)
    assert _sample("arbitrage_kill_switch_engaged") == 0


def test_daily_pnl_gauge_accepts_negative():
    metrics.daily_pnl_usd.set(-12.5)
    assert _sample("arbitrage_daily_pnl_usd") == -12.5


# ---- Histogram ------------------------------------------------------------


def test_leg_placement_histogram_observes_per_exchange():
    metrics.leg_placement_seconds.labels(exchange="binance").observe(0.012)
    metrics.leg_placement_seconds.labels(exchange="binance").observe(0.150)
    count = _sample(
        "arbitrage_leg_placement_seconds_count", exchange="binance",
    )
    assert count == 2


# ---- HTTP exposition ------------------------------------------------------


@pytest.mark.asyncio
async def test_serve_metrics_returns_prometheus_text():
    """The endpoint binds to 127.0.0.1 on a random free port, returns
    the exposition format, and serves whatever's currently in the
    module-local registry."""
    metrics.opportunities_total.labels(strategy="spatial").inc()
    runner = await metrics.serve_metrics(port=0)
    try:
        # `port=0` gives the OS a free port; read it off the runner.
        site = next(iter(runner.sites))  # type: ignore[attr-defined]
        port = site._server.sockets[0].getsockname()[1]  # type: ignore[union-attr]
        async with aiohttp.ClientSession() as session:
            async with session.get(f"http://127.0.0.1:{port}/metrics") as resp:
                assert resp.status == 200
                body = await resp.text()
        assert "arbitrage_opportunities_total" in body
        # Counter line carries the label + value.
        assert 'strategy="spatial"' in body
    finally:
        await metrics.stop_metrics()


@pytest.mark.asyncio
async def test_serve_metrics_is_idempotent():
    """Calling `serve_metrics` twice without an intervening
    `stop_metrics` returns the same runner — no port-bind conflict."""
    runner_a = await metrics.serve_metrics(port=0)
    try:
        runner_b = await metrics.serve_metrics(port=0)
        assert runner_a is runner_b
    finally:
        await metrics.stop_metrics()


@pytest.mark.asyncio
async def test_stop_metrics_safe_when_not_started():
    """No active runner → silent no-op."""
    await metrics.stop_metrics()  # must not raise
