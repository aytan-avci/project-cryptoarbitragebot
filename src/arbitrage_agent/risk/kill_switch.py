"""Kill-switch — durable boolean flag with audit reason.

Per `skills/risk-management/SKILL.md § The Kill-Switch`. State lives in a
JSON file (path from `Settings`). Sync I/O — kill-switch fires rarely;
the cost of `aiofiles` is not worth the dependency.
"""

import json
from datetime import datetime, timezone
from pathlib import Path

_DEFAULT_PAYLOAD = {"engaged": False}


def _read(path: Path) -> dict:
    if not path.exists():
        return dict(_DEFAULT_PAYLOAD)
    try:
        return json.loads(path.read_text())
    except (json.JSONDecodeError, OSError):
        # Unreadable file → treat as not-engaged. Operator alert is the
        # observability layer's job; risk only reports the read state.
        return dict(_DEFAULT_PAYLOAD)


def is_engaged(path: Path) -> bool:
    """True if the kill-switch is currently set. Defaults to False when
    the file is absent or unreadable."""
    return bool(_read(path).get("engaged", False))


def engage(path: Path, reason: str) -> None:
    """Idempotent. Writes audit info. Creates parent dir if missing."""
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "engaged": True,
        "reason": reason,
        "engaged_at_utc": datetime.now(timezone.utc).isoformat(),
    }
    path.write_text(json.dumps(payload, indent=2))


def reset(path: Path) -> None:
    """Manual reset. Operator action only; never call from the agent's
    own paths (kill-switch resets are an out-of-band decision)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "engaged": False,
        "reset_at_utc": datetime.now(timezone.utc).isoformat(),
    }
    path.write_text(json.dumps(payload, indent=2))
