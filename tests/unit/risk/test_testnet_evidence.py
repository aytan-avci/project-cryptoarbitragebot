"""S7 — testnet-probation evidence module (Faz 7g-d)."""

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from arbitrage_agent.risk.testnet_evidence import (
    REQUIRED_DAYS,
    attest_mainnet_eligibility,
    load,
    record,
)


_T0 = datetime(2026, 1, 1, tzinfo=timezone.utc)


def test_load_missing_file_returns_empty(tmp_path: Path):
    ev = load(tmp_path / "nope.json")
    assert ev.first_seen_utc is None
    assert ev.last_seen_utc is None
    assert ev.venues == ()
    assert ev.days_observed(_T0) == 0


def test_record_creates_file_with_first_and_last_seen(tmp_path: Path):
    p = tmp_path / "evidence.json"
    record("binance-testnet", _T0, p)
    data = json.loads(p.read_text())
    assert data["first_seen_utc"] == _T0.isoformat()
    assert data["last_seen_utc"] == _T0.isoformat()
    assert data["venues"] == ["binance-testnet"]


def test_record_preserves_first_seen_across_calls(tmp_path: Path):
    p = tmp_path / "evidence.json"
    record("binance-testnet", _T0, p)
    later = _T0 + timedelta(days=5)
    record("binance-testnet", later, p)
    ev = load(p)
    assert ev.first_seen_utc == _T0
    assert ev.last_seen_utc == later


def test_record_accumulates_venues(tmp_path: Path):
    p = tmp_path / "evidence.json"
    record("binance-testnet", _T0, p)
    record("bybit-testnet", _T0 + timedelta(days=1), p)
    ev = load(p)
    assert set(ev.venues) == {"binance-testnet", "bybit-testnet"}


def test_days_observed_zero_when_same_day(tmp_path: Path):
    p = tmp_path / "evidence.json"
    record("binance-testnet", _T0, p)
    ev = load(p)
    assert ev.days_observed(_T0 + timedelta(hours=23)) == 0


def test_days_observed_full_day_after_24h(tmp_path: Path):
    p = tmp_path / "evidence.json"
    record("binance-testnet", _T0, p)
    ev = load(p)
    assert ev.days_observed(_T0 + timedelta(days=1)) == 1


def test_attest_no_evidence_insufficient(tmp_path: Path):
    p = tmp_path / "evidence.json"
    ok, msg = attest_mainnet_eligibility(p, now=_T0, min_days=REQUIRED_DAYS)
    assert ok is False
    assert "no testnet evidence" in msg


def test_attest_insufficient_days_reports_count(tmp_path: Path):
    p = tmp_path / "evidence.json"
    record("binance-testnet", _T0, p)
    ok, msg = attest_mainnet_eligibility(
        p, now=_T0 + timedelta(days=10), min_days=30,
    )
    assert ok is False
    assert "10/30" in msg


def test_attest_sufficient_after_threshold(tmp_path: Path):
    p = tmp_path / "evidence.json"
    record("binance-testnet", _T0, p)
    ok, msg = attest_mainnet_eligibility(
        p, now=_T0 + timedelta(days=30), min_days=30,
    )
    assert ok is True
    assert "30 testnet days" in msg
    assert "binance-testnet" in msg


def test_attest_handles_malformed_evidence_file(tmp_path: Path):
    """A garbled evidence file must be treated as missing (gate
    rejects) — never as 'looks fine, allow mainnet'."""
    p = tmp_path / "evidence.json"
    p.write_text("{ not valid json")
    ok, msg = attest_mainnet_eligibility(p, now=_T0, min_days=30)
    assert ok is False
    assert "no testnet evidence" in msg


def test_record_is_atomic_per_call(tmp_path: Path):
    """Each `record` rewrites the file, so a partial write that's then
    re-read should still parse. We verify by alternating record/load
    five times — no corruption accumulates."""
    p = tmp_path / "evidence.json"
    for i in range(5):
        record("binance-testnet", _T0 + timedelta(days=i), p)
        ev = load(p)
        assert ev.first_seen_utc == _T0
        assert ev.last_seen_utc == _T0 + timedelta(days=i)
