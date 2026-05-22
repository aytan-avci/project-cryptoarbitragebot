"""`SystemClock` — the default `Clock` implementation.

Lives in `orchestration/` (not `strategies/`) because `strategies/` is
pure-by-construction and forbids `time` imports (AST-enforced). The
orchestrator builds a `SystemClock`, hands it to strategies via the
`Clock` protocol, and is the single point where wall-clock state enters
the system.

Tests inject a `FakeClock` (defined locally per test); see
`tests/unit/orchestration/test_clock.py` for the reference fake.
"""

import time


class SystemClock:
    """Wall-clock UTC milliseconds since epoch."""

    def now_ms(self) -> int:
        return int(time.time() * 1000)
