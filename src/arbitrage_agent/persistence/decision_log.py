"""Append-only JSON-lines decision log with SHA-256 hash chain.

Per `specs/ARCHITECTURE.md § 2.7`. Every `Opportunity`, `RiskDecision`,
`Fill`, and `MarketSnapshot` (Faz 7a) appends one line. Operator and
audit can replay history.

Faz 7g-b adds a tamper-evident hash chain:
- Each line carries `_prev_hash` (SHA-256 of the previous line's
  canonical content) and `_hash` (SHA-256 of THIS line's canonical
  content minus the `_hash` field itself).
- The first line's `_prev_hash` is `GENESIS_HASH` ("0" × 64).
- `verify_chain(path)` walks the file and checks every link; any
  missing field, JSON corruption, mid-chain edit, or out-of-order
  reordering breaks the chain and is reported with a line number.
- The `scripts/verify_audit_chain.py` CLI wraps `verify_chain` and
  exits 1 on tamper for CI / cron use.

Hash is stdlib `hashlib.sha256` (SECURITY.md S6 — no third-party
crypto). Computation is over canonical sorted-key JSON so identical
content always hashes the same regardless of dict iteration order.
"""

import hashlib
import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

from arbitrage_agent.domain import Fill, MarketSnapshot, Opportunity, RiskDecision

GENESIS_HASH = "0" * 64
"""Sentinel `_prev_hash` for the very first line of any chain."""


def _serialize(payload: dict) -> str:
    """Dict → one JSON line. Non-stdlib types (Decimal, datetime, Symbol)
    fall through `default=str`, which produces stable, parseable output."""
    return json.dumps(payload, sort_keys=True, default=str)


def _compute_hash(payload_with_prev_hash: dict) -> str:
    """SHA-256 of the canonical-JSON serialization of `payload`. The
    payload MUST already include `_prev_hash` but NOT `_hash`."""
    canonical = _serialize(payload_with_prev_hash)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class DecisionLog:
    """JSON-lines append-only writer with tamper-evident hash chain."""

    def __init__(self, path: Path) -> None:
        self._path = path
        self._last_hash = GENESIS_HASH
        self._restore_chain_state()

    @property
    def path(self) -> Path:
        return self._path

    @property
    def last_hash(self) -> str:
        """Hash of the most recently appended line, or GENESIS_HASH if
        the log is empty / new. Exposed for tests + recovery flows."""
        return self._last_hash

    # ---- Internals ------------------------------------------------------

    def _restore_chain_state(self) -> None:
        """Read the tail of an existing log to pick up the chain where
        the previous process left off. If the last line is missing
        `_hash` (legacy pre-Faz-7g-b log), the chain restarts from
        GENESIS for new appends — a subsequent verify will flag the
        boundary."""
        if not self._path.exists() or self._path.stat().st_size == 0:
            return
        try:
            with self._path.open("rb") as f:
                # Read up to last 32 KB — enough to contain the last
                # multi-event JSONL line even with verbose payloads.
                size = f.seek(0, 2)
                f.seek(max(0, size - 32_768))
                tail = f.read().decode("utf-8", errors="ignore")
            last_line = tail.strip().rsplit("\n", 1)[-1]
            if not last_line:
                return
            entry = json.loads(last_line)
            recovered = entry.get("_hash")
            if isinstance(recovered, str) and len(recovered) == 64:
                self._last_hash = recovered
        except (OSError, json.JSONDecodeError):
            # Corrupt tail — start fresh; verify_chain will report it.
            pass

    def _append(self, payload: dict) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        # Compute hash over payload + prev_hash; the hash field itself
        # is then injected on the final line.
        with_prev = {**payload, "_prev_hash": self._last_hash}
        new_hash = _compute_hash(with_prev)
        final = {**with_prev, "_hash": new_hash}
        with self._path.open("a", encoding="utf-8") as f:
            f.write(_serialize(final) + "\n")
        self._last_hash = new_hash

    # ---- Append helpers per event type ----------------------------------

    def append_opportunity(self, opp: Opportunity) -> None:
        self._append({
            "event": "opportunity_detected",
            "id": opp.id,
            "detected_at": opp.detected_at,
            "strategy": opp.strategy,
            "expected_net_profit_usd": opp.expected_net_profit,
            "confidence": opp.confidence,
            "valid_for_ms": opp.valid_for_ms,
            "legs": [asdict(leg) for leg in opp.legs],
        })

    def append_decision(self, decision: RiskDecision) -> None:
        self._append({
            "event": "risk_decision",
            "opportunity_id": decision.opportunity_id,
            "approved": decision.approved,
            "reason": decision.reason,
            "adjusted_quantity": decision.adjusted_quantity,
        })

    def append_fill(self, fill: Fill) -> None:
        self._append({
            "event": "fill",
            "opportunity_id": fill.opportunity_id,
            "exchange": fill.exchange,
            "symbol": str(fill.symbol),
            "side": fill.side,
            "price": fill.price,
            "volume": fill.volume,
            "fee": fill.fee,
            "timestamp_utc": fill.timestamp_utc,
        })

    def append_snapshot(self, snapshot: MarketSnapshot) -> None:
        self._append({
            "event": "snapshot_fetched",
            "exchange": snapshot.exchange,
            "symbol": str(snapshot.symbol),
            "bid": snapshot.bid,
            "ask": snapshot.ask,
            "bid_size": snapshot.bid_size,
            "ask_size": snapshot.ask_size,
            "timestamp_utc": snapshot.timestamp_utc,
        })


# ---- Verification ---------------------------------------------------------


def verify_chain(path: Path) -> tuple[bool, str, int]:
    """Walk the audit log line by line, checking every chain link.

    Returns `(ok, message, lines_checked)`. `ok=False` indicates
    tampering or corruption; `message` carries the first violation
    encountered with its line number.
    """
    if not path.exists():
        return False, f"audit log not found: {path}", 0

    prev_hash = GENESIS_HASH
    line_no = 0
    with path.open("r", encoding="utf-8") as f:
        for raw in f:
            line_no += 1
            raw = raw.rstrip("\n")
            if not raw.strip():
                continue
            try:
                entry: dict[str, Any] = json.loads(raw)
            except json.JSONDecodeError as exc:
                return False, f"line {line_no}: invalid JSON: {exc}", line_no
            if "_hash" not in entry:
                return (
                    False,
                    f"line {line_no}: missing `_hash` field "
                    "(legacy pre-Faz-7g-b line, or stripped)",
                    line_no,
                )
            if "_prev_hash" not in entry:
                return (
                    False,
                    f"line {line_no}: missing `_prev_hash` field",
                    line_no,
                )
            if entry["_prev_hash"] != prev_hash:
                return (
                    False,
                    f"line {line_no}: _prev_hash mismatch "
                    f"(chain broken — line inserted, deleted, or reordered)",
                    line_no,
                )
            without_self_hash = {k: v for k, v in entry.items() if k != "_hash"}
            expected = _compute_hash(without_self_hash)
            if entry["_hash"] != expected:
                return (
                    False,
                    f"line {line_no}: _hash mismatch (line content tampered)",
                    line_no,
                )
            prev_hash = entry["_hash"]
    return True, f"verified {line_no} line(s); chain intact", line_no
