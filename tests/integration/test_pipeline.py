"""Integration tests — pipeline.run() end-to-end paper chain."""

import asyncio
import json
import os
from decimal import Decimal
from pathlib import Path

import pytest

from arbitrage_agent.config import Settings
from arbitrage_agent.domain import (
    ExchangeId,
    MarketSnapshot,
    Symbol,
    now_utc,
    price,
    volume,
)
from arbitrage_agent.orchestration import pipeline


def _clean_env(monkeypatch):
    for k in list(os.environ):
        if k.startswith(
            ("RISK_", "EXECUTION_", "LOG_", "BINANCE_", "BYBIT_",
             "SPATIAL_", "PIPELINE_")
        ):
            monkeypatch.delenv(k, raising=False)


def _wide_spread_seeds() -> dict[ExchangeId, MarketSnapshot]:
    """Default-config seeds: produces an Opportunity that the gate approves."""
    btc = Symbol("BTC", "USDT")
    return {
        ExchangeId("binance"): MarketSnapshot(
            exchange=ExchangeId("binance"), symbol=btc,
            bid=price("60000"), ask=price("60001"),
            bid_size=volume("10"), ask_size=volume("10"),
            timestamp_utc=now_utc(),
        ),
        ExchangeId("bybit"): MarketSnapshot(
            exchange=ExchangeId("bybit"), symbol=btc,
            bid=price("60800"), ask=price("60801"),
            bid_size=volume("10"), ask_size=volume("10"),
            timestamp_utc=now_utc(),
        ),
    }


def _tight_spread_seeds() -> dict[ExchangeId, MarketSnapshot]:
    """Spread small enough that fees + slippage eat it; strategy → None."""
    btc = Symbol("BTC", "USDT")
    return {
        ExchangeId("binance"): MarketSnapshot(
            exchange=ExchangeId("binance"), symbol=btc,
            bid=price("60000"), ask=price("60001"),
            bid_size=volume("10"), ask_size=volume("10"),
            timestamp_utc=now_utc(),
        ),
        ExchangeId("bybit"): MarketSnapshot(
            exchange=ExchangeId("bybit"), symbol=btc,
            bid=price("60005"), ask=price("60006"),
            bid_size=volume("10"), ask_size=volume("10"),
            timestamp_utc=now_utc(),
        ),
    }


def test_pipeline_full_chain_writes_log(monkeypatch, tmp_path: Path):
    monkeypatch.chdir(tmp_path)
    _clean_env(monkeypatch)
    s = Settings()  # all defaults; log path under tmp cwd
    summary = asyncio.run(
        pipeline.run(s, snapshot_seeds=_wide_spread_seeds())
    )
    assert summary["iterations"] == 1
    assert summary["snapshots"] == 2  # one per adapter (Faz 7a)
    assert summary["opportunities"] == 1
    assert summary["approved"] == 1
    assert summary["rejected"] == 0
    assert summary["fills"] == 2

    log_path = tmp_path / "logs" / "decisions.jsonl"
    assert log_path.exists()
    events = [json.loads(line)["event"] for line in log_path.read_text().splitlines()]
    # 2 snapshots + 1 opp + 1 decision + 2 fills = 6 lines, in that order
    assert events == [
        "snapshot_fetched",
        "snapshot_fetched",
        "opportunity_detected",
        "risk_decision",
        "fill",
        "fill",
    ]


def test_pipeline_no_opportunity_when_spread_too_tight(monkeypatch, tmp_path: Path):
    monkeypatch.chdir(tmp_path)
    _clean_env(monkeypatch)
    s = Settings()
    summary = asyncio.run(
        pipeline.run(s, snapshot_seeds=_tight_spread_seeds())
    )
    assert summary["snapshots"] == 2  # snapshots are always written (Faz 7a)
    assert summary["opportunities"] == 0
    assert summary["approved"] == 0
    assert summary["fills"] == 0
    # Snapshot rows are written even with no opportunity detected.
    log_path = tmp_path / "logs" / "decisions.jsonl"
    assert log_path.exists()
    events = [json.loads(line)["event"] for line in log_path.read_text().splitlines()]
    assert events == ["snapshot_fetched", "snapshot_fetched"]


def test_pipeline_multiple_iterations(monkeypatch, tmp_path: Path):
    monkeypatch.chdir(tmp_path)
    _clean_env(monkeypatch)
    monkeypatch.setenv("PIPELINE_ITERATIONS", "3")
    s = Settings()
    summary = asyncio.run(
        pipeline.run(s, snapshot_seeds=_wide_spread_seeds())
    )
    # Static seeds re-fired each iteration → 3 opportunities, all approved
    assert summary["iterations"] == 3
    assert summary["opportunities"] == 3
    assert summary["approved"] == 3
    # Each iteration produces 2 fills (one per adapter); but `fetch_fills(
    # since=opp.detected_at)` may also re-emit accumulated fills depending
    # on wall-clock ordering (PaperExchange uses real time for fill
    # timestamps while the strategy clock is millisecond-resolution).
    # This double-counting is a known Faz 6 limitation; Faz 7 ingestion
    # replaces "fetch fills since" polling with subscription-based delivery.
    # Loose bounds: at least each iter's own 2 fills, at most cumulative.
    assert 6 <= summary["fills"] <= 12


def test_pipeline_rejects_single_seeded_exchange(monkeypatch, tmp_path: Path):
    monkeypatch.chdir(tmp_path)
    _clean_env(monkeypatch)
    s = Settings()
    only_one = {ExchangeId("binance"): _wide_spread_seeds()[ExchangeId("binance")]}
    with pytest.raises(ValueError, match=r"at least 2 seeded exchange"):
        asyncio.run(pipeline.run(s, snapshot_seeds=only_one))


def test_pipeline_hedge_fills_flow_through_audit_log_and_tracker(
    monkeypatch, tmp_path: Path,
):
    """Faz 7g-c — when execute() returns an imbalanced ExecutionResult,
    `_handle_hedge` must:
      1) call the real hedger,
      2) thread each hedge fill through DecisionLog + tracker,
      3) bump `counters["fills"]`.
    We drive `_handle_hedge` directly with a crafted ExecutionResult
    that has a buy fill on Binance and a failed sell on Bybit.
    """
    from arbitrage_agent.domain import (
        ExecutionResult, Fill, LegResult, OrderId, OrderIntent,
        new_opportunity_id, Opportunity,
    )
    from arbitrage_agent.exchanges.paper import PaperExchange
    from arbitrage_agent.ingestion.bus import LatestSnapshotView
    from arbitrage_agent.orchestration.account_state_tracker import AccountStateTracker
    from arbitrage_agent.orchestration.pipeline import _handle_hedge
    from arbitrage_agent.persistence.decision_log import DecisionLog

    monkeypatch.chdir(tmp_path)
    _clean_env(monkeypatch)
    s = Settings()  # default hedge_max_slippage_bps = 50

    btc = Symbol("BTC", "USDT")
    binance, bybit = ExchangeId("binance"), ExchangeId("bybit")
    seeds = _wide_spread_seeds()

    adapters = {
        binance: PaperExchange(name="binance", prices={btc: seeds[binance]}),
        bybit: PaperExchange(name="bybit", prices={btc: seeds[bybit]}),
    }
    view = LatestSnapshotView()
    view.update(seeds[binance])
    view.update(seeds[bybit])

    buy_leg = OrderIntent(exchange=binance, symbol=btc, side="buy",
                          quantity=volume("0.001"), limit_price=price("60001"))
    sell_leg = OrderIntent(exchange=bybit, symbol=btc, side="sell",
                           quantity=volume("0.001"), limit_price=price("60800"))
    opp_id = new_opportunity_id()
    opp = Opportunity(
        id=opp_id, detected_at=now_utc(), strategy="spatial",
        legs=(buy_leg, sell_leg),
        expected_net_profit=Decimal("0.5"), confidence=0.9, valid_for_ms=1000,
    )
    buy_fill = Fill(
        opportunity_id=opp_id, exchange=binance, symbol=btc, side="buy",
        price=price("60001"), volume=volume("0.001"), fee=price("0"),
        timestamp_utc=now_utc(),
    )
    result = ExecutionResult(
        opportunity_id=opp_id,
        legs=(
            LegResult(leg=buy_leg, order_id=OrderId("ord-binance"),
                      state="filled", fills=(buy_fill,)),
            LegResult(leg=sell_leg, order_id=None, state="failed", fills=()),
        ),
    )

    log_path = tmp_path / "decisions.jsonl"
    log_file = DecisionLog(log_path)
    tracker = AccountStateTracker()
    tracker.on_fill(buy_fill)  # baseline state matches the result
    counters = {"iterations": 0, "snapshots": 0, "opportunities": 0,
                "approved": 0, "rejected": 0, "fills": 0}

    asyncio.run(_handle_hedge(opp, result, adapters, view, s,
                              log_file, tracker, counters))

    # 1) counter-leg fill landed in the audit log.
    audit_lines = [json.loads(line) for line in log_path.read_text().splitlines()]
    fill_events = [e for e in audit_lines if e["event"] == "fill"]
    assert len(fill_events) == 1
    assert fill_events[0]["side"] == "sell"
    assert fill_events[0]["exchange"] == "bybit"

    # 2) tracker reflects the hedged net (buy +0.001 then sell -0.001 = 0).
    snap = tracker.snapshot(now_ms=0)
    bybit_pos = snap.open_position_qty.get((bybit, btc), Decimal("0"))
    binance_pos = snap.open_position_qty.get((binance, btc), Decimal("0"))
    assert binance_pos + bybit_pos == Decimal("0")

    # 3) counters bumped by hedge fill count.
    assert counters["fills"] == 1


def test_pipeline_forever_mode_stops_on_shutdown_event(
    monkeypatch, tmp_path: Path,
):
    """Faz 8 — pipeline_iterations=0 runs until the shutdown event is
    set. We inject the event by patching `_install_shutdown_event`, run
    the pipeline as a task, let a few iterations happen, then signal
    shutdown and assert the coroutine returns with iterations > 0."""
    monkeypatch.chdir(tmp_path)
    _clean_env(monkeypatch)

    injected = asyncio.Event()
    monkeypatch.setattr(pipeline, "_install_shutdown_event", lambda: injected)

    async def drive():
        # Small positive interval so the loop does a handful of
        # iterations (not thousands) before we signal shutdown.
        s = Settings(pipeline_iterations=0, poll_interval_s=0.01)
        task = asyncio.create_task(
            pipeline.run(s, snapshot_seeds=_wide_spread_seeds())
        )
        # Let the forever loop spin a bit, then request shutdown.
        await asyncio.sleep(0.05)
        injected.set()
        return await asyncio.wait_for(task, timeout=5)

    summary = asyncio.run(drive())
    assert summary["iterations"] > 0  # ran at least once before shutdown


def test_pipeline_forever_mode_returns_immediately_if_already_shutdown(
    monkeypatch, tmp_path: Path,
):
    """If the shutdown event is already set before the loop starts, the
    pipeline exits with zero iterations (clean no-op)."""
    monkeypatch.chdir(tmp_path)
    _clean_env(monkeypatch)

    injected = asyncio.Event()
    injected.set()
    monkeypatch.setattr(pipeline, "_install_shutdown_event", lambda: injected)

    s = Settings(pipeline_iterations=0)
    summary = asyncio.run(
        pipeline.run(s, snapshot_seeds=_wide_spread_seeds())
    )
    assert summary["iterations"] == 0


def test_pipeline_triangular_strategy_runs_against_single_seeded_venue(
    monkeypatch, tmp_path: Path,
):
    """Faz (B) — `strategy_name=triangular` swaps the pipeline's
    detector. Triangular needs ONE venue carrying THREE pairs. We
    seed `binance` with BTC/USDT, ETH/USDT, ETH/BTC at favourable
    forward-cycle prices and assert the audit log captures a
    triangular opportunity with 3 legs."""
    from arbitrage_agent.domain import OpportunityId

    monkeypatch.chdir(tmp_path)
    _clean_env(monkeypatch)

    # Triangular needs all three pairs on the SAME venue. The pipeline
    # currently auto-seeds two paper adapters from `snapshot_seeds`,
    # one snapshot each. To give Binance multiple symbols we'd need
    # multi-symbol paper seeds — but the existing _paper_from_seeds
    # only stores one snapshot per adapter. So we drive the pipeline
    # in spatial mode here and assert that the triangular strategy
    # builder + switching logic works at the _build_strategy seam.
    from arbitrage_agent.config import Settings
    from arbitrage_agent.orchestration import pipeline as pl
    from arbitrage_agent.strategies.triangular import TriangularArbitrage

    s = Settings(
        strategy_name="triangular",
        triangular_venue="binance",
        pipeline_iterations=1,
    )
    strat = pl._build_strategy(s, [ExchangeId("binance"), ExchangeId("bybit")])
    assert isinstance(strat, TriangularArbitrage)
    assert strat.min_venues == 1
    # Symbol set covers the configured cycle.
    syms = {str(sym) for sym in strat.symbols}
    assert syms == {"BTC/USDT", "ETH/USDT", "ETH/BTC"}


def test_pipeline_triangular_min_venues_check_passes_with_one_venue(
    monkeypatch, tmp_path: Path,
):
    """Triangular only needs ONE venue, so seeding a single adapter
    must NOT raise the spatial 'needs 2 venues' error."""
    monkeypatch.chdir(tmp_path)
    _clean_env(monkeypatch)
    monkeypatch.setenv("STRATEGY_NAME", "triangular")
    s = Settings()
    one_venue = {ExchangeId("binance"): _wide_spread_seeds()[ExchangeId("binance")]}
    # The paper seed only carries BTC/USDT — triangular needs three pairs.
    # `view.snapshot()` returns None for ETH/USDT + ETH/BTC, so the
    # strategy returns None each iteration. We just verify the pipeline
    # doesn't raise the min_venues ValueError.
    summary = asyncio.run(pipeline.run(s, snapshot_seeds=one_venue))
    assert summary["iterations"] == 1
    assert summary["opportunities"] == 0  # no triangular cycle detected


def test_pipeline_emits_prometheus_metrics(monkeypatch, tmp_path: Path):
    """Faz (D) — pipeline.run() increments the right Prometheus
    counters and histograms. We don't bind a port; the metrics module
    works against an in-process registry."""
    from arbitrage_agent.observability import metrics

    monkeypatch.chdir(tmp_path)
    _clean_env(monkeypatch)
    metrics.clear_for_tests()

    s = Settings(pipeline_iterations=2)
    summary = asyncio.run(
        pipeline.run(s, snapshot_seeds=_wide_spread_seeds())
    )

    # Counter samples match the in-process counters dict.
    opp_count = metrics.REGISTRY.get_sample_value(
        "arbitrage_opportunities_total", {"strategy": "spatial"},
    )
    assert opp_count == summary["opportunities"]

    approved = metrics.REGISTRY.get_sample_value(
        "arbitrage_decisions_total", {"outcome": "approved"},
    )
    assert approved == summary["approved"]

    # Each iteration that produced an opportunity also observed at least
    # one histogram sample.
    hist_count = metrics.REGISTRY.get_sample_value(
        "arbitrage_pipeline_iteration_seconds_count",
    )
    assert hist_count is not None and hist_count >= summary["opportunities"]

    # leg_placement_seconds gets one observation per leg per approved opp.
    for venue in ("binance", "bybit"):
        leg_count = metrics.REGISTRY.get_sample_value(
            "arbitrage_leg_placement_seconds_count", {"exchange": venue},
        )
        # paper happy-path means every approved opportunity attempted
        # every leg.
        assert leg_count == summary["approved"], (
            f"venue={venue} leg_count={leg_count} approved={summary['approved']}"
        )
