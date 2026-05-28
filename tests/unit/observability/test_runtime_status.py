"""Runtime status file — redacted dashboard state (Faz 8 part 2)."""

import json
from pathlib import Path

from arbitrage_agent.observability.runtime_status import write_status


def test_write_status_roundtrips(tmp_path: Path):
    p = tmp_path / "runtime_status.json"
    write_status(p, {"mode": "paper", "iterations": 5})
    data = json.loads(p.read_text())
    assert data["mode"] == "paper"
    assert data["iterations"] == 5
    assert "last_updated_utc" in data  # stamped automatically


def test_write_status_creates_parent_dirs(tmp_path: Path):
    p = tmp_path / "deep" / "nested" / "runtime_status.json"
    write_status(p, {"mode": "live"})
    assert p.exists()


def test_write_status_overwrites(tmp_path: Path):
    p = tmp_path / "runtime_status.json"
    write_status(p, {"iterations": 1})
    write_status(p, {"iterations": 2})
    assert json.loads(p.read_text())["iterations"] == 2
