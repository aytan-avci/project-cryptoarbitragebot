"""S7 — 30-day testnet probation evidence (Faz 7g-d).

Per `specs/SECURITY.md § S7`. A new live adapter must operate on
testnet for ≥30 consecutive days before mainnet is enabled. Until
Faz 7g-d this was operator policy; this module enforces it
programmatically.

Mechanism:

* Each successful authenticated call against a TESTNET URL invokes
  `record(venue, now)` on this module. The first record stamps
  `first_seen_utc`; every record bumps `last_seen_utc` and the venue
  set. State lives at `logs/testnet_evidence.json`.
* `Settings._confirm_mainnet_live` validator (`config.py`) calls
  `attest_mainnet_eligibility(...)` when execution_mode=live AND a
  mainnet URL is set. Insufficient evidence → ValueError; the
  process refuses to start.
* `S7_OVERRIDE_TESTNET_PROBATION=true` is the explicit emergency
  bypass. The override is logged loudly at startup and the operator
  is expected to record the rationale in
  `MEMORY.md § Decisions & Why`.

Pure JSON state (no DB), stdlib-only. The file lives in `logs/`
which is gitignored — evidence is per-environment.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_PATH = Path("logs/testnet_evidence.json")
"""Default location, relative to CWD where `python -m arbitrage_agent` runs."""

REQUIRED_DAYS = 30
"""S7 probation period."""


@dataclass(frozen=True, slots=True)
class TestnetEvidence:
    """Snapshot of recorded testnet activity. Immutable; rebuild via
    `record(...)` which writes-then-loads."""

    first_seen_utc: datetime | None
    last_seen_utc: datetime | None
    venues: tuple[str, ...]

    def days_observed(self, now: datetime) -> int:
        """Whole-day count between first_seen and `now`. Returns 0 if
        nothing has been recorded yet."""
        if self.first_seen_utc is None:
            return 0
        delta = now - self.first_seen_utc
        return max(0, delta.days)

    def is_sufficient(self, now: datetime, min_days: int = REQUIRED_DAYS) -> bool:
        return self.days_observed(now) >= min_days


def _empty() -> TestnetEvidence:
    return TestnetEvidence(first_seen_utc=None, last_seen_utc=None, venues=())


def load(path: Path = DEFAULT_PATH) -> TestnetEvidence:
    """Read the evidence file. Malformed or missing → empty evidence
    (the gate will report it as insufficient, surfacing the issue at
    enforcement time rather than crashing the bot)."""
    if not path.exists():
        return _empty()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        first = data.get("first_seen_utc")
        last = data.get("last_seen_utc")
        return TestnetEvidence(
            first_seen_utc=datetime.fromisoformat(first) if first else None,
            last_seen_utc=datetime.fromisoformat(last) if last else None,
            venues=tuple(data.get("venues", [])),
        )
    except (json.JSONDecodeError, ValueError, OSError):
        return _empty()


def record(venue: str, now: datetime, path: Path = DEFAULT_PATH) -> None:
    """Stamp testnet activity. First call sets `first_seen_utc`; every
    call refreshes `last_seen_utc` and adds `venue` to the venue set.
    Writes synchronously — the JSON is tiny and this is called from
    authenticated paths that already pay HTTP latency."""
    current = load(path)
    first = current.first_seen_utc or now
    venues = tuple(sorted(set(current.venues) | {venue}))
    payload = {
        "first_seen_utc": first.isoformat(),
        "last_seen_utc": now.isoformat(),
        "venues": list(venues),
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def attest_mainnet_eligibility(
    path: Path = DEFAULT_PATH,
    *,
    now: datetime | None = None,
    min_days: int = REQUIRED_DAYS,
) -> tuple[bool, str]:
    """Returns `(ok, message)`. `ok=True` only when there is recorded
    evidence AND `days_observed >= min_days`. The message describes
    the state in operator-friendly terms (first_seen date + day count
    + venue list) so the gate failure is actionable."""
    eff_now = now or datetime.now(timezone.utc)
    ev = load(path)
    if ev.first_seen_utc is None:
        return False, (
            f"S7: no testnet evidence at {path}; run testnet for "
            f"≥{min_days} days before enabling mainnet."
        )
    days = ev.days_observed(eff_now)
    if days < min_days:
        return False, (
            f"S7: only {days}/{min_days} testnet days observed "
            f"(first_seen={ev.first_seen_utc.date()}, "
            f"venues={list(ev.venues)})."
        )
    return True, (
        f"S7: {days} testnet days observed since "
        f"{ev.first_seen_utc.date()} across venues {list(ev.venues)}."
    )
