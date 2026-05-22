"""ExponentialBackoff helper."""

import pytest

from arbitrage_agent.ingestion.reconnect import ExponentialBackoff


def test_first_call_returns_initial_within_jitter():
    bo = ExponentialBackoff(initial_s=1.0, factor=2.0, max_s=30.0, jitter_ratio=0.1)
    d = bo.next()
    # initial=1.0 ± 10% jitter
    assert 0.9 <= d <= 1.1


def test_doubles_each_attempt():
    bo = ExponentialBackoff(initial_s=1.0, factor=2.0, max_s=30.0, jitter_ratio=0)
    delays = [bo.next() for _ in range(4)]
    assert delays == [1.0, 2.0, 4.0, 8.0]


def test_caps_at_max():
    bo = ExponentialBackoff(initial_s=1.0, factor=10.0, max_s=5.0, jitter_ratio=0)
    delays = [bo.next() for _ in range(4)]
    # 1, 10→5 (capped), 100→5, 1000→5
    assert delays == [1.0, 5.0, 5.0, 5.0]


def test_reset_returns_to_initial():
    bo = ExponentialBackoff(initial_s=1.0, factor=2.0, max_s=30.0, jitter_ratio=0)
    bo.next(); bo.next(); bo.next()
    assert bo.attempt == 3
    bo.reset()
    assert bo.attempt == 0
    assert bo.next() == 1.0


def test_rejects_bad_params():
    with pytest.raises(ValueError):
        ExponentialBackoff(initial_s=0)
    with pytest.raises(ValueError):
        ExponentialBackoff(initial_s=1, factor=1.0)
    with pytest.raises(ValueError):
        ExponentialBackoff(initial_s=1, max_s=-5)


def test_floor_at_min_delay():
    """Even with negative jitter, delay never goes below 0.1s."""
    bo = ExponentialBackoff(initial_s=0.1, factor=2.0, max_s=1.0, jitter_ratio=0.5)
    for _ in range(20):
        assert bo.next() >= 0.1
