"""Config tests — .env resolution, env-var override, validation."""

import pytest
from pydantic import ValidationError

from arbitrage_agent.config import Settings


def _clean_env(monkeypatch):
    """Strip every env var the Settings class looks at."""
    for name in (
        "EXECUTION_MODE",
        "LOG_LEVEL",
        "BINANCE_API_KEY",
        "BINANCE_API_SECRET",
        "BYBIT_API_KEY",
        "BYBIT_API_SECRET",
        "BINANCE_ENABLED",
        "BINANCE_REST_BASE_URL",
        "LIVE_TRADING_CONFIRMED",
        "S7_OVERRIDE_TESTNET_PROBATION",
        "S7_MIN_TESTNET_DAYS",
    ):
        monkeypatch.delenv(name, raising=False)


def _bypass_s7(monkeypatch):
    """Faz 7g-d — S7 testnet-probation gate is now automated. Tests
    that only exercise the S4 mainnet-confirmation path bypass S7
    explicitly so we don't conflate the two gates."""
    monkeypatch.setenv("S7_OVERRIDE_TESTNET_PROBATION", "true")


def test_defaults_are_safe(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    _clean_env(monkeypatch)
    s = Settings()
    assert s.execution_mode == "paper"
    assert s.log_level == "INFO"
    assert s.binance_api_key is None


def test_env_var_overrides_default(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    _clean_env(monkeypatch)
    monkeypatch.setenv("EXECUTION_MODE", "live")
    monkeypatch.setenv("LOG_LEVEL", "DEBUG")
    s = Settings()
    assert s.execution_mode == "live"
    assert s.log_level == "DEBUG"


def test_invalid_mode_rejected(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    _clean_env(monkeypatch)
    monkeypatch.setenv("EXECUTION_MODE", "yolo")
    with pytest.raises(ValidationError):
        Settings()


def test_env_file_loaded(monkeypatch, tmp_path):
    (tmp_path / ".env").write_text(
        "EXECUTION_MODE=live\nLOG_LEVEL=WARNING\nBINANCE_API_KEY=k\n"
    )
    monkeypatch.chdir(tmp_path)
    _clean_env(monkeypatch)
    s = Settings()
    assert s.execution_mode == "live"
    assert s.log_level == "WARNING"
    assert s.binance_api_key == "k"


def test_env_var_beats_env_file(monkeypatch, tmp_path):
    (tmp_path / ".env").write_text("EXECUTION_MODE=paper\n")
    monkeypatch.chdir(tmp_path)
    _clean_env(monkeypatch)
    monkeypatch.setenv("EXECUTION_MODE", "live")
    s = Settings()
    assert s.execution_mode == "live"


def test_case_insensitive_env(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    _clean_env(monkeypatch)
    monkeypatch.setenv("execution_mode", "live")  # lowercase env var
    s = Settings()
    assert s.execution_mode == "live"


# ---- SECURITY.md S4 — mainnet confirmation guard --------------------------


class TestMainnetConfirmation:
    def test_paper_mode_allows_any_url(self, monkeypatch, tmp_path):
        """Paper is always safe — base URL ignored."""
        monkeypatch.chdir(tmp_path)
        _clean_env(monkeypatch)
        monkeypatch.setenv("BINANCE_REST_BASE_URL", "https://api.binance.com")
        Settings()  # no raise

    def test_live_without_binance_enabled_allowed(self, monkeypatch, tmp_path):
        """live mode but binance_enabled=false → no live adapter is
        constructed → guard is unnecessary at this layer."""
        monkeypatch.chdir(tmp_path)
        _clean_env(monkeypatch)
        monkeypatch.setenv("EXECUTION_MODE", "live")
        Settings()  # no raise

    def test_live_testnet_allowed_without_confirmation(self, monkeypatch, tmp_path):
        monkeypatch.chdir(tmp_path)
        _clean_env(monkeypatch)
        monkeypatch.setenv("EXECUTION_MODE", "live")
        monkeypatch.setenv("BINANCE_ENABLED", "true")
        monkeypatch.setenv("BINANCE_REST_BASE_URL", "https://testnet.binance.vision")
        s = Settings()  # no raise
        assert "testnet" in s.binance_rest_base_url

    def test_live_mainnet_without_confirmation_rejected(self, monkeypatch, tmp_path):
        monkeypatch.chdir(tmp_path)
        _clean_env(monkeypatch)
        monkeypatch.setenv("EXECUTION_MODE", "live")
        monkeypatch.setenv("BINANCE_ENABLED", "true")
        # mainnet base URL (default value, but make it explicit for the test)
        monkeypatch.setenv("BINANCE_REST_BASE_URL", "https://api.binance.com")
        with pytest.raises(ValidationError, match="LIVE_TRADING_CONFIRMED"):
            Settings()

    def test_live_mainnet_with_confirmation_allowed(self, monkeypatch, tmp_path):
        monkeypatch.chdir(tmp_path)
        _clean_env(monkeypatch)
        _bypass_s7(monkeypatch)
        monkeypatch.setenv("EXECUTION_MODE", "live")
        monkeypatch.setenv("BINANCE_ENABLED", "true")
        monkeypatch.setenv("BINANCE_REST_BASE_URL", "https://api.binance.com")
        monkeypatch.setenv("LIVE_TRADING_CONFIRMED", "true")
        Settings()  # no raise

    def test_live_mainnet_with_confirmation_false_rejected(
        self, monkeypatch, tmp_path
    ):
        monkeypatch.chdir(tmp_path)
        _clean_env(monkeypatch)
        monkeypatch.setenv("EXECUTION_MODE", "live")
        monkeypatch.setenv("BINANCE_ENABLED", "true")
        monkeypatch.setenv("BINANCE_REST_BASE_URL", "https://api.binance.com")
        monkeypatch.setenv("LIVE_TRADING_CONFIRMED", "false")
        with pytest.raises(ValidationError):
            Settings()

    def test_bybit_mainnet_also_guarded(self, monkeypatch, tmp_path):
        """Faz 7d — S4 covers Bybit mainnet too."""
        monkeypatch.chdir(tmp_path)
        _clean_env(monkeypatch)
        monkeypatch.setenv("EXECUTION_MODE", "live")
        monkeypatch.setenv("BYBIT_ENABLED", "true")
        # default base url is mainnet api.bybit.com
        with pytest.raises(ValidationError, match="bybit"):
            Settings()

    def test_bybit_testnet_allowed(self, monkeypatch, tmp_path):
        monkeypatch.chdir(tmp_path)
        _clean_env(monkeypatch)
        monkeypatch.setenv("EXECUTION_MODE", "live")
        monkeypatch.setenv("BYBIT_ENABLED", "true")
        monkeypatch.setenv("BYBIT_REST_BASE_URL", "https://api-testnet.bybit.com")
        s = Settings()  # no raise
        assert "testnet" in s.bybit_rest_base_url

    def test_both_mainnet_with_confirmation_allowed(self, monkeypatch, tmp_path):
        monkeypatch.chdir(tmp_path)
        _clean_env(monkeypatch)
        _bypass_s7(monkeypatch)
        monkeypatch.setenv("EXECUTION_MODE", "live")
        monkeypatch.setenv("BINANCE_ENABLED", "true")
        monkeypatch.setenv("BYBIT_ENABLED", "true")
        monkeypatch.setenv("LIVE_TRADING_CONFIRMED", "true")
        Settings()  # no raise


# ---- SECURITY.md S7 — automated testnet probation gate (Faz 7g-d) ---------


class TestS7TestnetProbationGate:
    """`_confirm_mainnet_live` now also runs the S7 evidence check."""

    def test_mainnet_blocked_when_no_evidence(self, monkeypatch, tmp_path):
        monkeypatch.chdir(tmp_path)
        _clean_env(monkeypatch)
        monkeypatch.setenv("EXECUTION_MODE", "live")
        monkeypatch.setenv("BINANCE_ENABLED", "true")
        monkeypatch.setenv("BINANCE_REST_BASE_URL", "https://api.binance.com")
        monkeypatch.setenv("LIVE_TRADING_CONFIRMED", "true")
        # no evidence file under tmp_path → gate must refuse.
        with pytest.raises(ValidationError, match="S7"):
            Settings()

    def test_mainnet_blocked_when_evidence_too_recent(
        self, monkeypatch, tmp_path,
    ):
        from datetime import datetime, timedelta, timezone
        from arbitrage_agent.risk.testnet_evidence import record

        monkeypatch.chdir(tmp_path)
        _clean_env(monkeypatch)
        # Recorded testnet activity, but only 5 days ago.
        recent = datetime.now(timezone.utc) - timedelta(days=5)
        record("binance-testnet", recent, tmp_path / "logs" / "testnet_evidence.json")
        monkeypatch.setenv("EXECUTION_MODE", "live")
        monkeypatch.setenv("BINANCE_ENABLED", "true")
        monkeypatch.setenv("BINANCE_REST_BASE_URL", "https://api.binance.com")
        monkeypatch.setenv("LIVE_TRADING_CONFIRMED", "true")
        with pytest.raises(ValidationError, match=r"5/30 testnet days"):
            Settings()

    def test_mainnet_allowed_after_30_day_probation(
        self, monkeypatch, tmp_path,
    ):
        from datetime import datetime, timedelta, timezone
        from arbitrage_agent.risk.testnet_evidence import record

        monkeypatch.chdir(tmp_path)
        _clean_env(monkeypatch)
        long_ago = datetime.now(timezone.utc) - timedelta(days=31)
        record("binance-testnet", long_ago, tmp_path / "logs" / "testnet_evidence.json")
        monkeypatch.setenv("EXECUTION_MODE", "live")
        monkeypatch.setenv("BINANCE_ENABLED", "true")
        monkeypatch.setenv("BINANCE_REST_BASE_URL", "https://api.binance.com")
        monkeypatch.setenv("LIVE_TRADING_CONFIRMED", "true")
        Settings()  # no raise

    def test_explicit_override_bypasses_gate(self, monkeypatch, tmp_path):
        """Emergency override — must be explicit AND combined with the
        S4 confirmation. Operator is expected to record the rationale
        in MEMORY.md."""
        monkeypatch.chdir(tmp_path)
        _clean_env(monkeypatch)
        monkeypatch.setenv("EXECUTION_MODE", "live")
        monkeypatch.setenv("BINANCE_ENABLED", "true")
        monkeypatch.setenv("BINANCE_REST_BASE_URL", "https://api.binance.com")
        monkeypatch.setenv("LIVE_TRADING_CONFIRMED", "true")
        monkeypatch.setenv("S7_OVERRIDE_TESTNET_PROBATION", "true")
        Settings()  # no raise

    def test_testnet_url_skips_gate_even_without_evidence(
        self, monkeypatch, tmp_path,
    ):
        """Testnet URL → not a mainnet venue → S7 gate doesn't apply."""
        monkeypatch.chdir(tmp_path)
        _clean_env(monkeypatch)
        monkeypatch.setenv("EXECUTION_MODE", "live")
        monkeypatch.setenv("BINANCE_ENABLED", "true")
        monkeypatch.setenv("BINANCE_REST_BASE_URL", "https://testnet.binance.vision")
        s = Settings()  # no raise — testnet venue, no S4 + no S7 needed.
        assert "testnet" in s.binance_rest_base_url

    def test_lower_min_days_for_ci(self, monkeypatch, tmp_path):
        """`S7_MIN_TESTNET_DAYS` lets CI exercise the success path
        without 30-day fixture data."""
        from datetime import datetime, timedelta, timezone
        from arbitrage_agent.risk.testnet_evidence import record

        monkeypatch.chdir(tmp_path)
        _clean_env(monkeypatch)
        one_day_ago = datetime.now(timezone.utc) - timedelta(days=2)
        record("binance-testnet", one_day_ago, tmp_path / "logs" / "testnet_evidence.json")
        monkeypatch.setenv("EXECUTION_MODE", "live")
        monkeypatch.setenv("BINANCE_ENABLED", "true")
        monkeypatch.setenv("BINANCE_REST_BASE_URL", "https://api.binance.com")
        monkeypatch.setenv("LIVE_TRADING_CONFIRMED", "true")
        monkeypatch.setenv("S7_MIN_TESTNET_DAYS", "1")
        Settings()  # no raise — 2 days observed exceeds the override threshold.
