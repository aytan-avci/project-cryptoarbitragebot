"""Pipeline — wires ingestion → strategy → risk → execution.

Owns the asyncio event loop. Three operating modes:

* **Paper-only (default)** — synthetic snapshots seeded in-process; full
  strategy/risk/execution chain runs end-to-end against PaperExchange.
* **Live REST polling (Faz 7a–7d)** — when any `*_enabled` flag is on,
  pipeline polls each adapter's `fetch_book_snapshot` per iteration.
* **Live WebSocket (Faz 7c, opt-in via `INGESTION_MODE=ws`)** —
  event-driven: each adapter's `subscribe()` task pushes snapshots to
  a `MarketDataBus`, the bus invokes the strategy → risk → execution
  chain per snapshot. Runs for `WS_TIMEOUT_S` seconds, then shuts
  down cleanly.
"""

import asyncio
from decimal import Decimal

import structlog

from arbitrage_agent.config import Settings
from arbitrage_agent.domain import (
    Asset,
    ExchangeId,
    MarketSnapshot,
    Symbol,
    now_utc,
    price,
    volume,
)
from arbitrage_agent.exchanges.base import ExchangeAdapter
from arbitrage_agent.exchanges.paper import PaperExchange
from arbitrage_agent.exchanges.registry import build_live_adapters
from arbitrage_agent.execution.engine import execute
from arbitrage_agent.execution.hedger import hedge as run_hedge
from arbitrage_agent.observability import metrics
from arbitrage_agent.ingestion.bus import LatestSnapshotView, MarketDataBus
from arbitrage_agent.orchestration.account_state_tracker import AccountStateTracker
from arbitrage_agent.orchestration.clock import SystemClock
from arbitrage_agent.persistence.decision_log import DecisionLog
from arbitrage_agent.risk import kill_switch as ks_module
from arbitrage_agent.risk.gate import evaluate as risk_evaluate
from arbitrage_agent.risk.limits import limits_from_settings
from arbitrage_agent.strategies.base import Clock
from arbitrage_agent.strategies.spatial import SpatialArbitrage

_log = structlog.get_logger()
_BTC = Symbol("BTC", "USDT")


def _default_synthetic_snapshots() -> dict[ExchangeId, MarketSnapshot]:
    """Wide-spread seeds that clear default fees + slippage at default size,
    so a smoke run with no env overrides produces a visible approved chain."""
    binance = ExchangeId("binance")
    bybit = ExchangeId("bybit")
    return {
        binance: MarketSnapshot(
            exchange=binance, symbol=_BTC,
            bid=price("60000"), ask=price("60001"),
            bid_size=volume("10"), ask_size=volume("10"),
            timestamp_utc=now_utc(),
        ),
        bybit: MarketSnapshot(
            exchange=bybit, symbol=_BTC,
            bid=price("60800"), ask=price("60801"),
            bid_size=volume("10"), ask_size=volume("10"),
            timestamp_utc=now_utc(),
        ),
    }


def _paper_from_seeds(
    seeds: dict[ExchangeId, MarketSnapshot],
    taker_fee_bps: int,
) -> dict[ExchangeId, ExchangeAdapter]:
    out: dict[ExchangeId, ExchangeAdapter] = {}
    for exchange_id, snap in seeds.items():
        out[exchange_id] = PaperExchange(
            name=str(exchange_id),
            prices={snap.symbol: snap},
            taker_fee_bps=taker_fee_bps,
        )
    return out


async def run(
    settings: Settings,
    *,
    clock: Clock | None = None,
    snapshot_seeds: dict[ExchangeId, MarketSnapshot] | None = None,
) -> dict[str, int]:
    """Run the pipeline `settings.pipeline_iterations` times. Returns a
    counters dict for the caller to render as a summary line.

    Resolution order for adapter set:
      1. `snapshot_seeds` (test injection) — always paper.
      2. `build_live_adapters(settings)` — live exchanges that are enabled.
      3. `_default_synthetic_snapshots()` — paper fallback.
    """
    clk = clock or SystemClock()
    view = LatestSnapshotView()
    limits = limits_from_settings(settings)
    log_file = DecisionLog(settings.pipeline_decision_log_path)
    tracker = AccountStateTracker()

    # ----- choose adapter set -------------------------------------------
    if snapshot_seeds is not None:
        adapters = _paper_from_seeds(snapshot_seeds, settings.spatial_taker_fee_bps)
        mode = "paper"
    else:
        live = build_live_adapters(settings)
        if live:
            adapters = live
            mode = "live"
            _log.info("pipeline.live_mode", venues=sorted(adapters.keys()))
        else:
            adapters = _paper_from_seeds(
                _default_synthetic_snapshots(),
                settings.spatial_taker_fee_bps,
            )
            mode = "paper"

    counters = {
        "iterations": 0,
        "snapshots": 0,
        "opportunities": 0,
        "approved": 0,
        "rejected": 0,
        "fills": 0,
    }

    # ----- WebSocket mode (Faz 7c) ---------------------------------------
    if mode == "live" and settings.ingestion_mode == "ws":
        return await _run_ws(
            settings, adapters, view, limits, log_file, clk, counters, tracker,
        )

    # ----- single-venue live mode short-circuit -------------------------
    if mode == "live" and len(adapters) < 2:
        # Strategy needs ≥2 venues. Faz 7a's single-venue mode just shows
        # the live price and logs snapshots; Faz 7d (Bybit) restores the
        # full strategy chain.
        for _ in range(settings.pipeline_iterations):
            counters["iterations"] += 1
            for adapter in adapters.values():
                snap = await adapter.fetch_book_snapshot(_BTC)
                view.update(snap)
                log_file.append_snapshot(snap)
                tracker.on_snapshot(snap)
                counters["snapshots"] += 1
                _log.info(
                    "snapshot.fetched",
                    exchange=snap.exchange, symbol=str(snap.symbol),
                    bid=str(snap.bid), ask=str(snap.ask),
                    spread=str(snap.ask - snap.bid),
                )
        await _close_adapters(adapters)
        return counters

    # ----- full strategy chain (paper or multi-venue live) --------------
    exchange_ids = list(adapters.keys())
    if len(exchange_ids) < 2:
        raise ValueError("pipeline.run needs at least two seeded exchanges")
    strategy = SpatialArbitrage(
        symbol=_BTC,
        exchange_a=exchange_ids[0],
        exchange_b=exchange_ids[1],
        size=volume(str(settings.spatial_size_btc)),
        taker_fee_bps=settings.spatial_taker_fee_bps,
        slippage_usd_per_leg=settings.spatial_slippage_usd_per_leg,
        min_profit_threshold_usd=settings.spatial_min_profit_threshold_usd,
        valid_for_ms=settings.spatial_valid_for_ms,
        confidence=settings.spatial_confidence,
    )

    # Faz (D) — optional Prometheus exposition. Default off.
    metrics_runner = None
    if settings.metrics_enabled and settings.metrics_port > 0:
        metrics_runner = await metrics.serve_metrics(
            settings.metrics_port, settings.metrics_host,
        )
        _log.info(
            "pipeline.metrics_enabled",
            host=settings.metrics_host, port=settings.metrics_port,
        )

    for iter_idx in range(settings.pipeline_iterations):
        counters["iterations"] += 1

        with metrics.pipeline_iteration_seconds.time():
            # 0. Periodic balance polling (Faz 7g-a). Throttled by
            # `balance_poll_per_iterations`; 0 disables.
            if (
                settings.balance_poll_per_iterations > 0
                and iter_idx % settings.balance_poll_per_iterations == 0
            ):
                await _poll_balances(adapters, tracker, Asset("USDT"))

            # 1. Snapshots → view + audit log + tracker (Faz 7f freshness)
            for adapter in adapters.values():
                snap = await adapter.fetch_book_snapshot(_BTC)
                view.update(snap)
                log_file.append_snapshot(snap)
                tracker.on_snapshot(snap)
                counters["snapshots"] += 1

            # 2. Strategy
            opp = strategy.evaluate(view, clk)
            if opp is None:
                _log.info("pipeline.no_opportunity")
                continue
            counters["opportunities"] += 1
            metrics.opportunities_total.labels(strategy=opp.strategy).inc()
            _log.info(
                "opportunity.detected",
                id=opp.id,
                expected_net_profit_usd=str(opp.expected_net_profit),
                legs=len(opp.legs),
            )
            log_file.append_opportunity(opp)

            # 3. Risk gate — tracker snapshot carries Faz 7f state
            decision = risk_evaluate(opp, tracker.snapshot(clk.now_ms()), limits, clk.now_ms())
            log_file.append_decision(decision)
            if not decision.approved:
                counters["rejected"] += 1
                metrics.decisions_total.labels(outcome="rejected").inc()
                _log.info(
                    "risk.rejected",
                    opportunity_id=decision.opportunity_id,
                    reason=decision.reason,
                )
                continue
            counters["approved"] += 1
            metrics.decisions_total.labels(outcome="approved").inc()
            _log.info(
                "risk.approved",
                opportunity_id=decision.opportunity_id,
                reason=decision.reason,
            )

            # 4. Execute (concurrent, with per-leg timeout). Tracker records
            # the submission timestamps for the orders/min rolling cap.
            tracker.on_intent_submitted(list(opp.legs), clk.now_ms())
            result = await execute(opp, decision, adapters)
            _log.info(
                "execution.submitted",
                opportunity_id=opp.id,
                order_ids=[lr.order_id for lr in result.legs if lr.order_id],
                states=[lr.state for lr in result.legs],
            )

            # 5. Log per-leg fills + tracker positions + hedger alert if imbalanced
            for leg_result in result.legs:
                for fill in leg_result.fills:
                    log_file.append_fill(fill)
                    tracker.on_fill(fill)
                    counters["fills"] += 1
                    metrics.fills_total.labels(
                        exchange=str(fill.exchange), side=fill.side,
                    ).inc()
                    _log.info(
                        "execution.fill",
                        exchange=fill.exchange,
                        side=fill.side,
                        price=str(fill.price),
                        volume=str(fill.volume),
                        fee_usd=str(fill.fee),
                    )
            metrics.daily_pnl_usd.set(float(tracker.daily_pnl_usd))
            if result.needs_hedge:
                await _handle_hedge(
                    opp, result, adapters, view, settings,
                    log_file, tracker, counters,
                )

            # 6. Daily-loss auto-kill (Faz 7g-a). Runs after every iteration's
            # fills have updated tracker.daily_pnl_usd.
            engaged = _maybe_engage_daily_loss_kill(tracker, settings)
            if engaged:
                metrics.kill_switch_engaged.set(1)

    await _close_adapters(adapters)
    if metrics_runner is not None:
        await metrics.stop_metrics()
    return counters


async def _close_adapters(
    adapters: dict[ExchangeId, ExchangeAdapter],
) -> None:
    """Best-effort cleanup of HTTP sessions owned by live adapters."""
    for adapter in adapters.values():
        close = getattr(adapter, "close", None)
        if callable(close):
            try:
                await close()
            except Exception:  # noqa: BLE001
                pass


async def _poll_balances(
    adapters: dict[ExchangeId, ExchangeAdapter],
    tracker: AccountStateTracker,
    asset: Asset,
) -> None:
    """Faz 7g-a — Best-effort balance fetch per venue → tracker.set_cash.
    Live adapters return Decimal; paper adapters raise NotImplementedError
    (silently skipped). PermissionError comes from the S3 decorator in
    paper mode (also skipped). The result feeds the min_required_balance
    gate check (#10)."""
    for exchange_id, adapter in adapters.items():
        try:
            balance = await adapter.fetch_balance(asset)
        except (NotImplementedError, PermissionError):
            continue  # paper / wrong mode — no cash data, gate skips check
        except Exception as exc:  # noqa: BLE001
            _log.warning(
                "balance.fetch_failed",
                exchange=exchange_id,
                error=f"{type(exc).__name__}: {exc}",
            )
            continue
        tracker.set_cash(exchange_id, balance)
        _log.info(
            "balance.fetched",
            exchange=exchange_id, asset=asset, balance=str(balance),
        )


async def _handle_hedge(
    opp,
    result,
    adapters: dict[ExchangeId, ExchangeAdapter],
    view: LatestSnapshotView,
    settings: Settings,
    log_file: DecisionLog,
    tracker: AccountStateTracker,
    counters: dict[str, int],
) -> None:
    """Faz 7g-c — call the real hedger, then thread its fills through
    the same audit + tracker pipeline as the original execution fills.
    Counts hedge fills under the same `fills` counter so the summary
    line reflects total fills regardless of phase."""
    hedge_result = await run_hedge(
        opp, result, adapters, view, settings.hedge_max_slippage_bps,
    )
    for fill in hedge_result.fills:
        log_file.append_fill(fill)
        tracker.on_fill(fill)
        counters["fills"] += 1
        metrics.fills_total.labels(
            exchange=str(fill.exchange), side=fill.side,
        ).inc()
        _log.info(
            "hedger.fill",
            exchange=fill.exchange, side=fill.side,
            price=str(fill.price), volume=str(fill.volume),
            fee_usd=str(fill.fee),
        )
    metrics.hedge_results_total.labels(status=hedge_result.status).inc()
    # Audit-trail entry for the hedger decision itself — feeds the
    # dashboard's Hedge Activity panel (Faz (C)).
    log_file.append_hedger_result(hedge_result)
    _log.info(
        "hedger.result",
        opportunity_id=hedge_result.opportunity_id,
        status=hedge_result.status,
        remaining_exposure=str(hedge_result.remaining_exposure),
        reason=hedge_result.reason,
    )


def _maybe_engage_daily_loss_kill(
    tracker: AccountStateTracker,
    settings: Settings,
) -> bool:
    """Faz 7g-a — Auto-engage kill-switch when realised daily P&L
    breaches `risk_max_loss_per_day_usd`. Returns True iff engagement
    fired this call (caller can log it once)."""
    pnl = tracker.daily_pnl_usd
    if pnl >= -settings.risk_max_loss_per_day_usd:
        return False
    # Engage on disk (durable) AND on tracker (in-memory for this run)
    reason = (
        f"daily_loss_breach: realised P&L {pnl} < "
        f"-{settings.risk_max_loss_per_day_usd}"
    )
    try:
        ks_module.engage(settings.risk_kill_switch_path, reason=reason)
    except OSError as exc:
        _log.warning("kill_switch.engage_disk_failed", error=str(exc))
    tracker.set_kill_switch(True)
    _log.error(
        "kill_switch.auto_engaged",
        trigger="daily_loss",
        daily_pnl_usd=str(pnl),
        cap_usd=str(settings.risk_max_loss_per_day_usd),
        reason=reason,
    )
    return True


async def _run_ws(
    settings: Settings,
    adapters: dict[ExchangeId, ExchangeAdapter],
    view: LatestSnapshotView,
    limits,
    log_file: DecisionLog,
    clk: Clock,
    counters: dict[str, int],
    tracker: AccountStateTracker | None = None,
) -> dict[str, int]:
    """Event-driven WS pipeline. Runs for `settings.ws_timeout_s`, then
    cancels subscription tasks and returns."""
    if tracker is None:
        tracker = AccountStateTracker()
    exchange_ids = list(adapters.keys())
    has_strategy = len(exchange_ids) >= 2
    strategy = None
    if has_strategy:
        strategy = SpatialArbitrage(
            symbol=_BTC,
            exchange_a=exchange_ids[0],
            exchange_b=exchange_ids[1],
            size=volume(str(settings.spatial_size_btc)),
            taker_fee_bps=settings.spatial_taker_fee_bps,
            slippage_usd_per_leg=settings.spatial_slippage_usd_per_leg,
            min_profit_threshold_usd=settings.spatial_min_profit_threshold_usd,
            valid_for_ms=settings.spatial_valid_for_ms,
            confidence=settings.spatial_confidence,
        )

    bus = MarketDataBus()
    chain_lock = asyncio.Lock()  # serialize the strategy → risk → execute chain

    async def on_snapshot(snap):
        async with chain_lock:
            view.update(snap)
            log_file.append_snapshot(snap)
            tracker.on_snapshot(snap)
            counters["snapshots"] += 1
            _log.info(
                "snapshot.fetched",
                exchange=snap.exchange, symbol=str(snap.symbol),
                bid=str(snap.bid), ask=str(snap.ask),
                spread=str(snap.ask - snap.bid),
            )
            if strategy is None:
                return
            opp = strategy.evaluate(view, clk)
            if opp is None:
                return
            counters["opportunities"] += 1
            metrics.opportunities_total.labels(strategy=opp.strategy).inc()
            log_file.append_opportunity(opp)
            decision = risk_evaluate(opp, tracker.snapshot(clk.now_ms()), limits, clk.now_ms())
            log_file.append_decision(decision)
            if not decision.approved:
                counters["rejected"] += 1
                metrics.decisions_total.labels(outcome="rejected").inc()
                _log.info(
                    "risk.rejected",
                    opportunity_id=decision.opportunity_id,
                    reason=decision.reason,
                )
                return
            counters["approved"] += 1
            metrics.decisions_total.labels(outcome="approved").inc()
            _log.info(
                "risk.approved",
                opportunity_id=decision.opportunity_id,
                reason=decision.reason,
            )
            tracker.on_intent_submitted(list(opp.legs), clk.now_ms())
            result = await execute(opp, decision, adapters)
            _log.info(
                "execution.submitted",
                opportunity_id=opp.id,
                order_ids=[lr.order_id for lr in result.legs if lr.order_id],
                states=[lr.state for lr in result.legs],
            )
            for leg_result in result.legs:
                for fill in leg_result.fills:
                    log_file.append_fill(fill)
                    tracker.on_fill(fill)
                    counters["fills"] += 1
                    metrics.fills_total.labels(
                        exchange=str(fill.exchange), side=fill.side,
                    ).inc()
                    _log.info(
                        "execution.fill",
                        exchange=fill.exchange, side=fill.side,
                        price=str(fill.price), volume=str(fill.volume),
                        fee_usd=str(fill.fee),
                    )
            metrics.daily_pnl_usd.set(float(tracker.daily_pnl_usd))
            if result.needs_hedge:
                await _handle_hedge(
                    opp, result, adapters, view, settings,
                    log_file, tracker, counters,
                )

            # Daily-loss auto-kill (Faz 7g-a)
            if _maybe_engage_daily_loss_kill(tracker, settings):
                metrics.kill_switch_engaged.set(1)

    bus.subscribe(on_snapshot)

    # Launch each adapter's subscribe task; they push to the bus.
    async def adapter_task(adapter):
        await adapter.subscribe([_BTC], bus.publish)

    tasks = [asyncio.create_task(adapter_task(a)) for a in adapters.values()]
    _log.info(
        "pipeline.ws_mode_started",
        venues=sorted(adapters.keys()),
        timeout_s=settings.ws_timeout_s,
        strategy="spatial" if has_strategy else "none (single venue)",
    )

    try:
        await asyncio.wait_for(
            asyncio.gather(*tasks, return_exceptions=True),
            timeout=settings.ws_timeout_s,
        )
    except asyncio.TimeoutError:
        pass  # expected exit — timeout fires after WS_TIMEOUT_S
    finally:
        for t in tasks:
            t.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        await _close_adapters(adapters)

    _log.info("pipeline.ws_mode_stopped", **counters)
    return counters
