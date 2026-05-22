"""Build the active adapter map from `Settings`.

Per `skills/exchange-integration/SKILL.md § Adding a New Exchange step 5`:
the registry is the one-liner that hooks each new adapter into the system.
"""

from arbitrage_agent.config import Settings
from arbitrage_agent.domain import ExchangeId
from arbitrage_agent.exchanges.base import ExchangeAdapter
from arbitrage_agent.exchanges.binance import BinanceAdapter
from arbitrage_agent.exchanges.bybit import BybitAdapter


def build_live_adapters(settings: Settings) -> dict[ExchangeId, ExchangeAdapter]:
    """Construct one adapter per enabled live exchange. Returns `{}` if all
    `*_enabled` flags are False — the pipeline then falls back to its
    paper-only default."""
    adapters: dict[ExchangeId, ExchangeAdapter] = {}
    if settings.binance_enabled:
        adapters[ExchangeId("binance")] = BinanceAdapter(
            base_url=settings.binance_rest_base_url,
            rate_limit_per_minute=settings.binance_rate_limit_per_min,
            ws_base_url=settings.binance_ws_base_url,
            api_key=settings.binance_api_key,
            api_secret=settings.binance_api_secret,
        )
    if settings.bybit_enabled:
        adapters[ExchangeId("bybit")] = BybitAdapter(
            base_url=settings.bybit_rest_base_url,
            rate_limit_per_minute=settings.bybit_rate_limit_per_min,
            ws_base_url=settings.bybit_ws_base_url,
        )
    # Faz 7e+ adds Coinbase / Kraken / etc.
    return adapters
