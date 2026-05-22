#!/usr/bin/env python3
"""Verify the SHA-256 hash chain of an audit log (`logs/decisions.jsonl`).

Per `specs/ARCHITECTURE.md § 2.7` (Faz 7g-b). Walks the JSONL file line
by line, checks every `_prev_hash` link, and recomputes every `_hash`.
Any mismatch — line tampered, inserted, deleted, or reordered — is
reported with the offending line number.

Exit codes:
    0 — chain intact
    1 — tamper, corruption, or file missing
    2 — invalid CLI invocation

Designed for CI / cron use:

    python scripts/verify_audit_chain.py logs/decisions.jsonl
"""

from __future__ import annotations

import sys
from pathlib import Path

# Make the in-repo `src/` importable when invoked as `python scripts/...`.
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from arbitrage_agent.persistence.decision_log import verify_chain  # noqa: E402


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print(f"usage: {argv[0]} <path-to-decisions.jsonl>", file=sys.stderr)
        return 2
    path = Path(argv[1])
    ok, message, lines = verify_chain(path)
    stream = sys.stdout if ok else sys.stderr
    print(message, file=stream)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
