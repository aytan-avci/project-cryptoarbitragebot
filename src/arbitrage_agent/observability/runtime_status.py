"""Redacted runtime status for the dashboard's read-only panel (Faz 8).

The bot writes `logs/runtime_status.json` so the dashboard can show
operational state (loop mode, notification config, P&L, kill-switch)
WITHOUT any web-writable config endpoint and WITHOUT ever exposing a
secret. Only booleans + non-secret values are written here — never
`smtp_password` / `telegram_bot_token`. The dashboard reads it the
same way it reads `decisions.jsonl`.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def write_status(path: Path, status: dict[str, Any]) -> None:
    """Atomically-ish write the redacted status dict. `last_updated_utc`
    is stamped automatically. Caller is responsible for ensuring no
    secret values are present in `status` (see callers in pipeline.py)."""
    payload = dict(status)
    payload["last_updated_utc"] = datetime.now(timezone.utc).isoformat()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
