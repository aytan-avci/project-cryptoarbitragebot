"""SystemClock — minimal wall-clock wrapper."""

import time

from arbitrage_agent.orchestration.clock import SystemClock
from arbitrage_agent.strategies.base import Clock


def test_system_clock_satisfies_clock_protocol():
    assert isinstance(SystemClock(), Clock)


def test_system_clock_returns_int_ms():
    c = SystemClock()
    t = c.now_ms()
    assert isinstance(t, int)


def test_system_clock_is_monotonic_enough():
    """Sequential calls return non-decreasing milliseconds within ~100ms."""
    c = SystemClock()
    a = c.now_ms()
    time.sleep(0.001)
    b = c.now_ms()
    assert b >= a


def test_system_clock_close_to_wall_time():
    c = SystemClock()
    wall_ms = int(time.time() * 1000)
    clock_ms = c.now_ms()
    # Should be within a tight window of stdlib's time.time()
    assert abs(clock_ms - wall_ms) < 100
