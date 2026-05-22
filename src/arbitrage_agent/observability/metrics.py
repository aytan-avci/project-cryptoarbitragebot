"""Prometheus metrics + HTTP exposition (Faz (D)).

Per `specs/QUALITY_ATTRIBUTES.md` — make pipeline behaviour observable
without coupling each module to a metrics backend. Modules import
named singletons from here and call `.inc()`, `.observe()`, `.set()`;
this module owns the `CollectorRegistry`, the HTTP endpoint, and the
naming convention.

Naming follows Prometheus best practice:
* `arbitrage_*` namespace for everything emitted by the bot.
* `_total` suffix on counters (`opportunities_total`,
  `decisions_total`, `fills_total`, `hedge_results_total`).
* `_seconds` suffix on duration histograms.
* Unit-suffixed gauges (`daily_pnl_usd`, `kill_switch_engaged`).

The histograms use bucket boundaries calibrated for spot-arb
latencies: an opportunity-to-fill pipeline iteration is typically
< 250 ms when paper, 1–5 s when live REST polling; a single
`place_order` call against Binance / Bybit is ~10–500 ms.

`serve_metrics(port)` runs an aiohttp app on a separate `TCPSite`
inside the existing asyncio loop — no new thread, no new event
loop. Default-off (`metrics_enabled=False` in Settings) so paper
smoke runs don't bind a port.

Stdlib + `prometheus_client` only. No registry-globals leakage:
every metric is bound to the module-local `REGISTRY` so unit tests
can verify exposition output without third-party globals interfering.
"""

from __future__ import annotations

from prometheus_client import (
    CONTENT_TYPE_LATEST,
    CollectorRegistry,
    Counter,
    Gauge,
    Histogram,
    generate_latest,
)


REGISTRY = CollectorRegistry()
"""Module-local registry — keeps `prometheus_client`'s default global
clean so tests don't carry state across modules."""


# ---- Counters -------------------------------------------------------------

opportunities_total = Counter(
    "arbitrage_opportunities_total",
    "Strategy-detected opportunities since process start.",
    ["strategy"],
    registry=REGISTRY,
)

decisions_total = Counter(
    "arbitrage_decisions_total",
    "Risk gate decisions; labelled by outcome.",
    ["outcome"],  # "approved" | "rejected"
    registry=REGISTRY,
)

fills_total = Counter(
    "arbitrage_fills_total",
    "Fills observed; labelled by venue and side.",
    ["exchange", "side"],
    registry=REGISTRY,
)

hedge_results_total = Counter(
    "arbitrage_hedge_results_total",
    "Hedger outcomes; labelled by status.",
    ["status"],  # filled | partial | aborted_slippage | no_market_data | placement_failed | no_imbalance
    registry=REGISTRY,
)


# ---- Histograms -----------------------------------------------------------

pipeline_iteration_seconds = Histogram(
    "arbitrage_pipeline_iteration_seconds",
    "End-to-end pipeline iteration latency (snapshot → strategy → "
    "risk → execution → hedge).",
    buckets=(0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0),
    registry=REGISTRY,
)

leg_placement_seconds = Histogram(
    "arbitrage_leg_placement_seconds",
    "Per-leg `place_order` call latency.",
    ["exchange"],
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0),
    registry=REGISTRY,
)


# ---- Gauges ---------------------------------------------------------------

kill_switch_engaged = Gauge(
    "arbitrage_kill_switch_engaged",
    "1 if the kill switch is engaged (durable file present), 0 otherwise.",
    registry=REGISTRY,
)

daily_pnl_usd = Gauge(
    "arbitrage_daily_pnl_usd",
    "Realised daily P&L (USD). Resets on UTC day rollover via the tracker.",
    registry=REGISTRY,
)


# ---- HTTP exposition ------------------------------------------------------

# Keep a module-level handle to the active runner so reentrant calls
# don't double-bind the port — the pipeline may call `serve_metrics`
# in both REST-poll and WS modes if config flips mid-session in tests.
_active_runner = None  # type: ignore[var-annotated]


async def serve_metrics(port: int, host: str = "127.0.0.1"):
    """Start an aiohttp `TCPSite` exposing `GET /metrics` in the
    Prometheus text exposition format. Returns the runner so the
    caller can `await runner.cleanup()` at shutdown.

    Idempotent: a second call while a runner is already active is a
    no-op and returns the existing runner."""
    global _active_runner
    if _active_runner is not None:
        return _active_runner

    from aiohttp import web

    async def handler(_request: "web.Request") -> "web.Response":
        # `CONTENT_TYPE_LATEST` includes a `charset=utf-8` parameter
        # which aiohttp's `content_type=` kwarg rejects. Pass it
        # through the raw `Content-Type` header instead.
        body = generate_latest(REGISTRY)
        return web.Response(body=body, headers={"Content-Type": CONTENT_TYPE_LATEST})

    app = web.Application()
    app.router.add_get("/metrics", handler)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, host, port)
    await site.start()
    _active_runner = runner
    return runner


async def stop_metrics() -> None:
    """Tear down the metrics HTTP server if one is active.
    Safe to call multiple times."""
    global _active_runner
    if _active_runner is None:
        return
    runner = _active_runner
    _active_runner = None
    await runner.cleanup()


# ---- Test helpers ---------------------------------------------------------


def _all_metrics() -> tuple:
    """All metric handles in declaration order — used by tests to
    isolate fixtures via `clear_for_tests()`."""
    return (
        opportunities_total,
        decisions_total,
        fills_total,
        hedge_results_total,
        pipeline_iteration_seconds,
        leg_placement_seconds,
        kill_switch_engaged,
        daily_pnl_usd,
    )


def clear_for_tests() -> None:
    """Reset LABELLED counters/histograms (`prometheus_client`'s
    `.clear()` drops every labelled child). Unlabelled metrics
    (`pipeline_iteration_seconds`, gauges) are NOT reset — tests for
    those should either use delta comparisons or assert via the
    exposition output. This intentional asymmetry keeps the
    test-helper out of `prometheus_client`'s private state."""
    for metric in (
        opportunities_total,
        decisions_total,
        fills_total,
        hedge_results_total,
        leg_placement_seconds,
    ):
        metric.clear()
    kill_switch_engaged.set(0)
    daily_pnl_usd.set(0)


def render() -> bytes:
    """Render the current registry to Prometheus text exposition.
    Equivalent to `curl /metrics`."""
    return generate_latest(REGISTRY)
