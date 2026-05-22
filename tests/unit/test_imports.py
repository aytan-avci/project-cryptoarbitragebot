"""Import smoke — every module in `arbitrage_agent` must import cleanly.

A NotImplementedError raised at *call time* is fine; a module that fails
at *import time* breaks the entire skeleton. This test fences that
regression.
"""

import importlib
import pkgutil

import arbitrage_agent

EXPECTED_MODULES = {
    "arbitrage_agent",
    "arbitrage_agent.__main__",
    "arbitrage_agent.config",
    "arbitrage_agent.domain",
    "arbitrage_agent.domain.events",
    "arbitrage_agent.domain.ids",
    "arbitrage_agent.domain.money",
    "arbitrage_agent.exchanges",
    "arbitrage_agent.exchanges.base",
    "arbitrage_agent.exchanges.binance",
    "arbitrage_agent.exchanges.bybit",
    "arbitrage_agent.exchanges.errors",
    "arbitrage_agent.exchanges.paper",
    "arbitrage_agent.exchanges.rate_limit",
    "arbitrage_agent.exchanges.registry",
    "arbitrage_agent.execution",
    "arbitrage_agent.execution.engine",
    "arbitrage_agent.execution.hedger",
    "arbitrage_agent.execution.reconciler",
    "arbitrage_agent.ingestion",
    "arbitrage_agent.ingestion.bus",
    "arbitrage_agent.ingestion.normalizer",
    "arbitrage_agent.ingestion.reconnect",
    "arbitrage_agent.observability",
    "arbitrage_agent.observability.alerts",
    "arbitrage_agent.observability.logging_setup",
    "arbitrage_agent.observability.metrics",
    "arbitrage_agent.orchestration",
    "arbitrage_agent.orchestration.account_state_tracker",
    "arbitrage_agent.orchestration.clock",
    "arbitrage_agent.orchestration.lifecycle",
    "arbitrage_agent.orchestration.pipeline",
    "arbitrage_agent.persistence",
    "arbitrage_agent.persistence.decision_log",
    "arbitrage_agent.persistence.fills",
    "arbitrage_agent.risk",
    "arbitrage_agent.risk.gate",
    "arbitrage_agent.risk.kill_switch",
    "arbitrage_agent.risk.limits",
    "arbitrage_agent.risk.testnet_evidence",
    "arbitrage_agent.strategies",
    "arbitrage_agent.strategies.base",
    "arbitrage_agent.strategies.funding_rate",
    "arbitrage_agent.strategies.spatial",
    "arbitrage_agent.strategies.triangular",
}


def _walk_all() -> set[str]:
    """Recursively enumerate every importable module under arbitrage_agent."""
    found: set[str] = {"arbitrage_agent"}
    for _finder, name, _is_pkg in pkgutil.walk_packages(
        arbitrage_agent.__path__, prefix="arbitrage_agent."
    ):
        found.add(name)
    return found


def test_every_module_imports():
    discovered = _walk_all()
    for name in sorted(discovered):
        importlib.import_module(name)


def test_module_set_matches_expected():
    """Catch silent additions or removals of modules in the source tree."""
    discovered = _walk_all()
    # `__main__` is not enumerated by pkgutil; assert separately
    importlib.import_module("arbitrage_agent.__main__")
    discovered.add("arbitrage_agent.__main__")
    missing = EXPECTED_MODULES - discovered
    extra = discovered - EXPECTED_MODULES
    assert not missing, f"expected but absent: {sorted(missing)}"
    assert not extra, f"present but not expected: {sorted(extra)}"


def test_exchange_adapter_protocol_imports():
    from arbitrage_agent.exchanges.base import ExchangeAdapter, SnapshotCallback

    # Regression guard: every member from `skills/exchange-integration/SKILL.md`
    # § The Protocol must be declared. Removing one is an architectural change.
    for member in (
        "id",
        "subscribe",
        "fetch_book_snapshot",
        "place_order",
        "cancel_order",
        "fetch_balance",
        "fetch_fills",
    ):
        assert hasattr(ExchangeAdapter, member), member
    assert SnapshotCallback is not None


def test_strategy_protocol_imports():
    from arbitrage_agent.strategies.base import Clock, MarketView, Strategy

    for proto in (Clock, MarketView, Strategy):
        assert proto is not None
    assert hasattr(Strategy, "evaluate")
    assert hasattr(MarketView, "snapshot")
    assert hasattr(Clock, "now_ms")


def test_account_state_constructs_empty():
    from arbitrage_agent.risk.limits import AccountState

    state = AccountState()
    assert state.cash_by_exchange == {}
    assert state.open_position_qty == {}


def test_gate_real_signature():
    """`risk/gate.evaluate` is now implemented (Faz 5b). Sentinel removed;
    full behaviour suite lives in `tests/unit/risk/test_gate.py`. This
    test only fences the public signature so an accidental reversion to
    a NotImplementedError-only stub would fail here as well."""
    import inspect
    from arbitrage_agent.risk.gate import evaluate

    sig = inspect.signature(evaluate)
    params = list(sig.parameters)
    assert params == ["opportunity", "state", "limits", "now_ms"]
