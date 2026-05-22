"""Smoke tests for the exception hierarchy."""

import pytest

from arbitrage_agent.exchanges import errors


def test_all_subclasses_of_exchange_error():
    for name in (
        "RateLimited",
        "InsufficientFunds",
        "OrderNotFound",
        "MarketHalted",
        "InvalidOrder",
        "TemporaryFailure",
        "PermanentFailure",
    ):
        cls = getattr(errors, name)
        assert issubclass(cls, errors.ExchangeError), name


def test_exchange_error_catches_all():
    with pytest.raises(errors.ExchangeError):
        raise errors.RateLimited("boom")
    with pytest.raises(errors.ExchangeError):
        raise errors.TemporaryFailure("blip")


def test_distinct_classes():
    # A handler discriminating on subtype must work.
    try:
        raise errors.RateLimited("429")
    except errors.PermanentFailure:
        pytest.fail("RateLimited should not match PermanentFailure")
    except errors.RateLimited:
        pass
