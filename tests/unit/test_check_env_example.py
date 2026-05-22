"""scripts/check_env_example.py — verify the env-example lint catches leaks.

We invoke the script as a subprocess against a tmp_path copy of
.env.example (or a synthetic file) so the test mirrors what
pre-commit / CI actually run.
"""

import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "check_env_example.py"


def _run_against(tmp_env_example_text: str, tmp_path: Path) -> subprocess.CompletedProcess:
    """Copy the script + the test text into tmp_path and invoke it from there."""
    (tmp_path / "scripts").mkdir(exist_ok=True)
    # The script resolves .env.example relative to its own location; copy it.
    target_script = tmp_path / "scripts" / "check_env_example.py"
    target_script.write_text(SCRIPT.read_text())
    (tmp_path / ".env.example").write_text(tmp_env_example_text)
    return subprocess.run(
        [sys.executable, str(target_script)],
        capture_output=True,
        text=True,
    )


def test_empty_values_pass(tmp_path: Path):
    body = (
        "EXECUTION_MODE=paper\n"
        "BINANCE_API_KEY=\n"
        "BINANCE_API_SECRET=\n"
        "LOG_LEVEL=INFO\n"
    )
    r = _run_against(body, tmp_path)
    assert r.returncode == 0, r.stdout + r.stderr


def test_real_looking_key_is_rejected(tmp_path: Path):
    body = (
        "EXECUTION_MODE=paper\n"
        "BINANCE_API_KEY=ABCDEF0123456789abcdef0123456789ABCDEF0123456789abcdef0123456789\n"
    )
    r = _run_against(body, tmp_path)
    assert r.returncode == 1
    assert "BINANCE_API_KEY" in r.stdout


def test_allowed_defaults_pass(tmp_path: Path):
    body = (
        "EXECUTION_MODE=paper\n"
        "BINANCE_REST_BASE_URL=https://api.binance.com\n"
        "INGESTION_MODE=poll\n"
        "BINANCE_ENABLED=false\n"
        "BINANCE_RATE_LIMIT_PER_MIN=60\n"
    )
    r = _run_against(body, tmp_path)
    assert r.returncode == 0, r.stdout + r.stderr


def test_unknown_value_caught(tmp_path: Path):
    body = "MYSTERY_FIELD=some-non-empty-value\n"
    r = _run_against(body, tmp_path)
    assert r.returncode == 1


def test_comments_and_blank_lines_ignored(tmp_path: Path):
    body = (
        "# Just a comment\n"
        "\n"
        "   \n"
        "BINANCE_API_KEY=\n"
    )
    r = _run_against(body, tmp_path)
    assert r.returncode == 0, r.stdout + r.stderr


def test_masks_long_values_in_output(tmp_path: Path):
    """Leak detection output must not echo the full secret."""
    secret = "ABCDEF0123456789abcdef0123456789ABCDEF0123456789abcdef0123456789"
    body = f"BINANCE_API_KEY={secret}\n"
    r = _run_against(body, tmp_path)
    assert secret not in r.stdout  # full secret not echoed
    assert "ABCD" in r.stdout and "6789" in r.stdout  # masked head+tail
