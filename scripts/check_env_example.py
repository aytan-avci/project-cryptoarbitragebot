#!/usr/bin/env python3
"""Verify `.env.example` contains only EMPTY placeholder values.

The template file is committed to the repo. Any non-empty value to the
right of `=` on a `KEY=value` line risks being a real credential
(SECURITY.md § 5.1 incident class). This script is invoked by the
pre-commit hook and CI; exit code 1 blocks the commit / pipeline.

Heuristic: every line of the form `IDENTIFIER=value` must have an
empty value, UNLESS the value matches one of the explicit allowlist
patterns (mode literals, base URLs, integer rate limits, …).
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ENV_EXAMPLE = Path(__file__).resolve().parent.parent / ".env.example"

# Values that are explicitly allowed in the template — they are not
# secrets, they are documented defaults / mode literals.
ALLOWED_VALUES = {
    "paper",                                  # EXECUTION_MODE default
    "poll",                                   # INGESTION_MODE default
    "false",                                  # *_ENABLED default
    "true",                                   # operator may set during review
    "INFO", "DEBUG", "WARNING", "ERROR",      # LOG_LEVEL choices
    "https://api.binance.com",
    "https://testnet.binance.vision",
    "https://api.bybit.com",
    "https://api-testnet.bybit.com",
    "60", "120", "30",                        # rate / timeout defaults
    "587",                                     # SMTP submission port (Faz 8)
}

# Lines we should skip entirely (comments, blank lines).
COMMENT_OR_BLANK = re.compile(r"^\s*(#.*)?$")

# KEY=value capture. We don't require the key to be uppercase only,
# but the convention is.
KV = re.compile(r"^([A-Z][A-Z0-9_]*)=(.*)$")


def main() -> int:
    if not ENV_EXAMPLE.exists():
        print(f"check_env_example: {ENV_EXAMPLE} not found")
        return 1

    bad: list[tuple[int, str, str]] = []
    for line_no, line in enumerate(ENV_EXAMPLE.read_text().splitlines(), start=1):
        if COMMENT_OR_BLANK.match(line):
            continue
        m = KV.match(line)
        if not m:
            continue
        key, value = m.group(1), m.group(2).strip()
        if value == "":
            continue
        if value in ALLOWED_VALUES:
            continue
        bad.append((line_no, key, value))

    if bad:
        print("❌ .env.example contains non-empty values that are not on the allowlist.")
        print("   This commonly indicates a real credential pasted into the template.")
        print("   Move the value to .env (gitignored) and clear it here.")
        print("   See specs/SECURITY.md § 5.1 if a real key was committed.\n")
        for line_no, key, value in bad:
            masked = value[:4] + "…" + value[-4:] if len(value) > 12 else value
            print(f"   line {line_no}: {key}={masked}")
        return 1

    print("✓ .env.example is clean (all values empty or allowlisted)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
