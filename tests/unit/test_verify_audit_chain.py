"""scripts/verify_audit_chain.py — CLI exit code contract.

The script is wired into CI / cron (SECURITY.md S6). Tampering must
flip exit code 0 → 1 so a non-zero return reliably trips an alert.
"""

import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "verify_audit_chain.py"


def _run(path: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SCRIPT), str(path)],
        capture_output=True,
        text=True,
    )


def _seed_clean_log(tmp_path: Path) -> Path:
    """Produce a small valid hash-chained log via the real writer."""
    # Importing here keeps test collection cheap when this file is skipped.
    sys.path.insert(0, str(REPO_ROOT / "src"))
    from arbitrage_agent.domain import (
        ExchangeId, Opportunity, OrderIntent, Symbol,
        new_opportunity_id, now_utc, price, volume,
    )
    from arbitrage_agent.persistence.decision_log import DecisionLog
    from decimal import Decimal

    log_path = tmp_path / "decisions.jsonl"
    log = DecisionLog(log_path)
    for _ in range(3):
        log.append_opportunity(Opportunity(
            id=new_opportunity_id(),
            detected_at=now_utc(),
            strategy="spatial",
            legs=(OrderIntent(
                exchange=ExchangeId("paper"),
                symbol=Symbol("BTC", "USDT"),
                side="buy",
                quantity=volume("0.001"),
                limit_price=price("60000"),
            ),),
            expected_net_profit=Decimal("0.5"),
            confidence=0.9,
            valid_for_ms=1000,
        ))
    return log_path


def test_clean_log_exits_zero(tmp_path: Path):
    log_path = _seed_clean_log(tmp_path)
    result = _run(log_path)
    assert result.returncode == 0, result.stderr
    assert "verified 3 line" in result.stdout


def test_tampered_log_exits_one(tmp_path: Path):
    log_path = _seed_clean_log(tmp_path)
    raw = log_path.read_text().splitlines()
    entry = json.loads(raw[1])
    entry["confidence"] = 0.0  # mutate without recomputing _hash
    raw[1] = json.dumps(entry, sort_keys=True, default=str)
    log_path.write_text("\n".join(raw) + "\n")

    result = _run(log_path)
    assert result.returncode == 1
    assert "line 2" in result.stderr


def test_missing_file_exits_one(tmp_path: Path):
    result = _run(tmp_path / "does-not-exist.jsonl")
    assert result.returncode == 1
    assert "not found" in result.stderr


def test_no_args_exits_two(tmp_path: Path):
    result = subprocess.run(
        [sys.executable, str(SCRIPT)],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 2
    assert "usage" in result.stderr
