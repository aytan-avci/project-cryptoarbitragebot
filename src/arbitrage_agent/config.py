"""Project configuration. Single source of truth for runtime settings.

Reads from environment variables and a `.env` file in the CWD (where
`python -m arbitrage_agent` is invoked). Pydantic-settings v2.
"""

import os
from decimal import Decimal
from pathlib import Path
from typing import Literal

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

ExecutionMode = Literal["paper", "live"]


class Settings(BaseSettings):
    """Read once at startup; treat the resulting instance as immutable."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    execution_mode: ExecutionMode = "paper"
    log_level: str = "INFO"

    # Exchange credentials. Trade-only, IP-whitelisted, no withdrawal
    # (CLAUDE.md § 2 C1). Optional in paper mode.
    binance_api_key: str | None = None
    binance_api_secret: str | None = None
    bybit_api_key: str | None = None
    bybit_api_secret: str | None = None

    # Risk limits (skills/risk-management/SKILL.md § Limits).
    # Defaults are intentionally tight — operator widens via .env, never
    # mid-flight. Freshness of an opportunity uses
    # `opportunity.valid_for_ms` (set by the strategy) per SKILL.md §
    # Decision Order; no global cap there.
    risk_min_profit_threshold_usd: Decimal = Decimal("0.50")
    risk_min_order_value_usd: Decimal = Decimal("20")
    risk_max_order_value_usd: Decimal = Decimal("200")
    risk_max_gross_exposure_usd: Decimal = Decimal("1500")
    # Faz 7f — three more SKILL.md checks
    risk_max_position_value_usd: Decimal = Decimal("500")
    risk_max_orders_per_minute: int = 30
    risk_max_snapshot_age_ms: int = 10_000  # venue stale ⇒ quarantined
    # Faz 7g-a — financial safety completion
    risk_min_required_balance_usd: Decimal = Decimal("50")
    risk_max_loss_per_day_usd: Decimal = Decimal("50")
    balance_poll_per_iterations: int = 5  # 0 disables polling

    # Faz 7g-c — hedger slippage budget. Worst acceptable drift between
    # the original leg's limit_price and current best market price when
    # the hedger places a counter-leg. SKILL.md § The Hedger: "Hedge at
    # a defined max slippage budget (config, e.g., 0.5%)".
    hedge_max_slippage_bps: int = 50  # 0.50%

    # Faz 7g-d — S7 testnet probation gate (SECURITY.md § S7). 30-day
    # probation before mainnet is enabled. `s7_min_testnet_days` allows
    # tests / CI to lower the threshold; production keeps the default.
    risk_testnet_evidence_path: Path = Path("logs/testnet_evidence.json")
    s7_min_testnet_days: int = 30

    # Faz (D) — Prometheus metrics exposition. Default off so paper
    # smoke runs don't bind a port. `metrics_port=0` is reserved as
    # "disabled" alongside `metrics_enabled=False` for explicit kill.
    metrics_enabled: bool = False
    metrics_port: int = 9090
    metrics_host: str = "127.0.0.1"

    # Kill-switch durable state (sync JSON). `logs/` is gitignored.
    risk_kill_switch_path: Path = Path("logs/kill_switch.json")

    # Strategy selector (Faz (B)). MVP supports one strategy per
    # deployment (CLAUDE.md C8); flip this env to swap.
    strategy_name: Literal["spatial", "triangular"] = "spatial"

    # Spatial strategy parameters (skills/arbitrage-detection/SKILL.md).
    # Per-strategy thresholds live in config (QA-5.3).
    spatial_size_btc: Decimal = Decimal("0.001")
    spatial_taker_fee_bps: int = 10  # 0.10% taker fee per leg
    spatial_slippage_usd_per_leg: Decimal = Decimal("0.01")
    spatial_min_profit_threshold_usd: Decimal = Decimal("0.50")
    spatial_valid_for_ms: int = 1000
    spatial_confidence: float = 0.9

    # Triangular strategy parameters (Faz (B)). Single-venue cycle
    # over three pairs: intermediate/quote, base/quote, base/intermediate.
    # Default cycle: USDT → BTC → ETH → USDT (and reverse) on the
    # configured venue. `triangular_venue` MUST match an enabled
    # adapter at runtime.
    triangular_venue: str = "binance"
    triangular_quote: str = "USDT"
    triangular_intermediate: str = "BTC"
    triangular_base: str = "ETH"
    triangular_size_quote: Decimal = Decimal("50")  # USDT notional
    triangular_taker_fee_bps: int = 10
    triangular_min_profit_threshold_usd: Decimal = Decimal("0.50")
    triangular_valid_for_ms: int = 1000
    triangular_confidence: float = 0.85

    # Orchestration / pipeline (Faz 6).
    # `pipeline_iterations=0` (Faz 8) means run FOREVER until SIGINT/
    # SIGTERM — the autonomous-daemon mode. Any positive N runs exactly
    # N iterations then exits (used by tests + one-shot smoke).
    pipeline_iterations: int = 1
    pipeline_decision_log_path: Path = Path("logs/decisions.jsonl")

    # Faz 8 — seconds to sleep between poll-mode iterations. 0 = no
    # sleep (fast finite test/smoke runs). Forever/live mode should set
    # a positive value (e.g. 2.0) to respect venue rate limits.
    poll_interval_s: float = 0.0

    # Faz 8 — redacted runtime status the bot writes for the dashboard's
    # read-only status panel. Contains booleans + non-secret values
    # ONLY (never SMTP password / Telegram token).
    runtime_status_path: Path = Path("logs/runtime_status.json")

    # Live exchanges (Faz 7a — read-only public REST; no API key required).
    # Default `False` keeps the synthetic-paper smoke path safe by default.
    binance_enabled: bool = False
    binance_rest_base_url: str = "https://api.binance.com"
    binance_rate_limit_per_min: int = 60  # 80% of Binance's public 75/min cap

    # Bybit (Faz 7d). Bybit V5 public REST allows ~600 requests / 5 sec;
    # 120/min is a conservative cap for spot top-of-book polling.
    bybit_enabled: bool = False
    bybit_rest_base_url: str = "https://api.bybit.com"
    bybit_rate_limit_per_min: int = 120

    # WebSocket ingestion (Faz 7c). `poll` keeps the existing REST loop;
    # `ws` switches to event-driven snapshots via each adapter's subscribe.
    # `ws_timeout_s` caps the WS run for smoke + CI runs.
    ingestion_mode: Literal["poll", "ws"] = "poll"
    ws_timeout_s: int = 30
    binance_ws_base_url: str = "wss://stream.binance.com:9443"
    bybit_ws_base_url: str = "wss://stream.bybit.com/v5/public/spot"

    # SECURITY.md S4 — mainnet live trading requires an additional explicit
    # confirmation env var. Runs after all fields are populated. Covers
    # every enabled venue with a mainnet URL.
    @model_validator(mode="after")
    def _confirm_mainnet_live(self) -> "Settings":
        if self.execution_mode != "live":
            return self

        mainnet_venues: list[str] = []
        if self.binance_enabled:
            url = self.binance_rest_base_url.lower()
            if "binance.com" in url and "testnet" not in url:
                mainnet_venues.append("binance")
        if self.bybit_enabled:
            url = self.bybit_rest_base_url.lower()
            if "bybit.com" in url and "testnet" not in url:
                mainnet_venues.append("bybit")

        if not mainnet_venues:
            return self  # all enabled venues point at testnet or are off

        confirmed = (
            os.environ.get("LIVE_TRADING_CONFIRMED", "").strip().lower() == "true"
        )
        if not confirmed:
            raise ValueError(
                f"execution_mode='live' + mainnet URL for "
                f"{mainnet_venues} requires LIVE_TRADING_CONFIRMED=true "
                "(CLAUDE.md C3 / SECURITY.md S4). For development, point "
                "at testnet URLs (e.g. https://testnet.binance.vision, "
                "https://api-testnet.bybit.com) and leave "
                "LIVE_TRADING_CONFIRMED unset."
            )

        # SECURITY.md S7 — automated 30-day testnet probation gate.
        # Local import keeps `config.py` loadable in environments where
        # `logs/` does not yet exist (the path is only consulted here).
        from arbitrage_agent.risk.testnet_evidence import (
            attest_mainnet_eligibility,
        )

        ok, message = attest_mainnet_eligibility(
            self.risk_testnet_evidence_path,
            min_days=self.s7_min_testnet_days,
        )
        override = (
            os.environ.get("S7_OVERRIDE_TESTNET_PROBATION", "")
            .strip().lower() == "true"
        )
        if not ok and not override:
            raise ValueError(
                f"{message} Refusing to start mainnet+live for "
                f"{mainnet_venues}. Emergency bypass: set "
                "S7_OVERRIDE_TESTNET_PROBATION=true AND record the "
                "rationale in MEMORY.md § Decisions & Why."
            )
        return self
