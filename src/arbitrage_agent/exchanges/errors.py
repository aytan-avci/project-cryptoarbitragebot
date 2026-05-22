"""Domain-level exception hierarchy for exchange operations.

Per `skills/exchange-integration/SKILL.md § Error Translation`. Each adapter
catches its native errors (aiohttp.ClientError, ccxt.ExchangeError, …) and
re-raises **one of these** before crossing the module boundary. The rest of
the system sees only these types.
"""


class ExchangeError(Exception):
    """Base — catch this to handle any exchange-side failure generically."""


class RateLimited(ExchangeError):
    """The exchange refused due to rate limiting. Adapter must back off."""


class InsufficientFunds(ExchangeError):
    """Account does not have the balance needed for the order."""


class OrderNotFound(ExchangeError):
    """Referenced order does not exist on the exchange."""


class MarketHalted(ExchangeError):
    """Trading on this symbol is currently halted by the exchange."""


class InvalidOrder(ExchangeError):
    """Order rejected by exchange (size / price / symbol invalid)."""


class TemporaryFailure(ExchangeError):
    """Retryable: network blip, exchange 5xx, ambiguous response."""


class PermanentFailure(ExchangeError):
    """Not retryable: bad auth, malformed request, deprecated endpoint."""
