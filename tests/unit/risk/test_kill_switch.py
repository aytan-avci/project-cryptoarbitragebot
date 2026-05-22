"""Tests for `risk/kill_switch.py` — durable JSON-file state."""

import json
from pathlib import Path

import pytest

from arbitrage_agent.risk import kill_switch as ks


def test_absent_file_is_not_engaged(tmp_path: Path):
    assert ks.is_engaged(tmp_path / "missing.json") is False


def test_engage_persists_state(tmp_path: Path):
    path = tmp_path / "k.json"
    ks.engage(path, reason="max_loss_breached")
    assert path.exists()
    data = json.loads(path.read_text())
    assert data["engaged"] is True
    assert data["reason"] == "max_loss_breached"
    assert "engaged_at_utc" in data


def test_engage_then_is_engaged(tmp_path: Path):
    path = tmp_path / "k.json"
    ks.engage(path, reason="manual")
    assert ks.is_engaged(path) is True


def test_engage_creates_parent_directories(tmp_path: Path):
    path = tmp_path / "deep" / "nested" / "k.json"
    ks.engage(path, reason="manual")
    assert path.exists()


def test_engage_is_idempotent(tmp_path: Path):
    path = tmp_path / "k.json"
    ks.engage(path, reason="first")
    ks.engage(path, reason="second")
    # Second engage overwrites; both calls should be safe
    data = json.loads(path.read_text())
    assert data["engaged"] is True
    assert data["reason"] == "second"


def test_reset_disengages(tmp_path: Path):
    path = tmp_path / "k.json"
    ks.engage(path, reason="manual")
    assert ks.is_engaged(path) is True
    ks.reset(path)
    assert ks.is_engaged(path) is False


def test_malformed_json_treated_as_not_engaged(tmp_path: Path):
    path = tmp_path / "k.json"
    path.write_text("this is not json {")
    # Read should not raise; treats unreadable as not-engaged
    assert ks.is_engaged(path) is False


def test_empty_file_treated_as_not_engaged(tmp_path: Path):
    path = tmp_path / "k.json"
    path.write_text("")
    assert ks.is_engaged(path) is False
