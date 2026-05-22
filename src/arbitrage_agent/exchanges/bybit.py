"""Bybit exchange adapter — REST only (Faz 7d).

Per `skills/exchange-integration/SKILL.md`. Scope:
- `fetch_book_snapshot(symbol)` → real GET `/v5/market/orderbook`
  on the spot category, via aiohttp.
- All other protocol methods raise `NotImplementedError` (Faz 7b+
  adds authenticated endpoints; Faz 7c adds WS).

Symbol notation matches Binance (`BTCUSDT`). Public endpoint, no API
key needed. Bybit returns HTTP 200 for application-level errors —
the discriminator is the `retCode` field (0 = success).
"""

import asyncio
import json
from datetime import datetime
from typing import Any

import aiohttp

from arbitrage_agent.ingestion.reconnect import ExponentialBackoff

from arbitrage_agent.domain import (
    Asset,
    ExchangeId,
    Fill,
    MarketSnapshot,
    OrderId,
    OrderIntent,
    RiskDecision,
    Symbol,
    Volume,
    now_utc,
    price,
    volume,
)
from arbitrage_agent.exchanges.base import SnapshotCallback, requires_live_mode
from arbitrage_agent.exchanges.errors import (
    ExchangeError,
    InvalidOrder,
    MarketHalted,
    PermanentFailure,
    RateLimited,
    TemporaryFailure,
)
from arbitrage_agent.exchanges.rate_limit import TokenBucket


class BybitAdapter:
    """Public-REST adapter for Bybit V5 spot."""

    DEFAULT_BASE_URL = "https://api.bybit.com"
    DEFAULT_WS_BASE_URL = "wss://stream.bybit.com/v5/public/spot"

    def __init__(
        self,
        base_url: str = DEFAULT_BASE_URL,
        rate_limit_per_minute: int = 120,
        session: aiohttp.ClientSession | None = None,
        request_timeout_s: float = 10.0,
        ws_base_url: str = DEFAULT_WS_BASE_URL,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._ws_base_url = ws_base_url
        self._bucket = TokenBucket(rate_per_minute=rate_limit_per_minute)
        self._session_owner = session is None
        self._session = session
        self._timeout = aiohttp.ClientTimeout(total=request_timeout_s)

    @property
    def id(self) -> ExchangeId:
        return ExchangeId("bybit")

    @staticmethod
    def _to_native(symbol: Symbol) -> str:
        """`Symbol('BTC','USDT')` → `'BTCUSDT'`."""
        return f"{symbol.base}{symbol.quote}"

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None:
            self._session = aiohttp.ClientSession(timeout=self._timeout)
        return self._session

    async def close(self) -> None:
        if self._session_owner and self._session is not None:
            await self._session.close()
            self._session = None

    # ---- ExchangeAdapter protocol ---------------------------------------

    async def fetch_book_snapshot(self, symbol: Symbol) -> MarketSnapshot:
        """Top-of-book snapshot via `/v5/market/orderbook?category=spot`."""
        await self._bucket.acquire()
        url = f"{self._base_url}/v5/market/orderbook"
        params = {
            "category": "spot",
            "symbol": self._to_native(symbol),
            "limit": "5",
        }
        session = await self._get_session()
        try:
            async with session.get(url, params=params) as resp:
                payload = await self._handle_response(resp, symbol)
        except aiohttp.ClientError as e:
            raise TemporaryFailure(f"bybit network error: {e}") from e
        except asyncio.TimeoutError:
            raise TemporaryFailure("bybit request timed out") from None

        return self._parse_book(symbol, payload)

    @staticmethod
    async def _handle_response(
        resp: aiohttp.ClientResponse, symbol: Symbol
    ) -> dict[str, Any]:
        # HTTP-layer issues (rare; bybit usually returns 200 even on error)
        if 500 <= resp.status < 600:
            raise TemporaryFailure(f"bybit {resp.status} (server error)")
        if resp.status == 429:
            raise RateLimited(f"bybit 429 on {symbol}")
        if resp.status != 200:
            raise ExchangeError(f"bybit unexpected status {resp.status}")

        body = await resp.json()
        ret_code = body.get("retCode")

        if ret_code == 0:
            return body

        # Application-layer error codes — mapping subset per
        # https://bybit-exchange.github.io/docs/v5/error
        ret_msg = body.get("retMsg", "unknown")
        if ret_code in (10006, 10018):  # rate limit / IP limit
            raise RateLimited(f"bybit retCode {ret_code}: {ret_msg}")
        if ret_code in (10001, 10002, 10004):  # invalid param / sign / args
            raise InvalidOrder(f"bybit retCode {ret_code}: {ret_msg}")
        if ret_code in (10005, 10010, 10016):  # permission / IP / system
            raise PermanentFailure(f"bybit retCode {ret_code}: {ret_msg}")
        # Unknown error code → retryable; log will surface for future mapping.
        raise TemporaryFailure(f"bybit retCode {ret_code}: {ret_msg}")

    def _parse_book(
        self, symbol: Symbol, payload: dict[str, Any]
    ) -> MarketSnapshot:
        try:
            result = payload["result"]
            bids = result["b"]
            asks = result["a"]
            if not bids or not asks:
                raise MarketHalted(f"empty book for {symbol}")
            best_bid_price, best_bid_size = bids[0]
            best_ask_price, best_ask_size = asks[0]
        except (KeyError, IndexError, TypeError, ValueError) as e:
            raise PermanentFailure(
                f"malformed bybit response: {e}"
            ) from e

        return MarketSnapshot(
            exchange=self.id,
            symbol=symbol,
            bid=price(str(best_bid_price)),
            ask=price(str(best_ask_price)),
            bid_size=volume(str(best_bid_size)),
            ask_size=volume(str(best_ask_size)),
            timestamp_utc=now_utc(),
        )

    # ---- Not implemented in Faz 7d -------------------------------------

    async def subscribe(
        self, symbols: list[Symbol], on_snapshot: SnapshotCallback
    ) -> None:
        """Subscribe to spot orderbook.1 channels for every symbol.

        Bybit V5 spot public WS: send `{"op":"subscribe","args":[
        "orderbook.1.BTCUSDT"]}` after connect, then receive frames
        of shape `{"topic":"orderbook.1.BTCUSDT","data":{"s":"BTCUSDT",
        "b":[["60000","1.0"]],"a":[["60001","0.8"]],"u":..., "seq":...}}`.

        Reconnects with exponential backoff. Loops until cancelled.
        """
        backoff = ExponentialBackoff()
        symbol_by_native = {self._to_native(s): s for s in symbols}
        topics = [f"orderbook.1.{native}" for native in symbol_by_native]

        while True:
            try:
                session = await self._get_session()
                async with session.ws_connect(
                    self._ws_base_url, heartbeat=20
                ) as ws:
                    await ws.send_json({"op": "subscribe", "args": topics})
                    backoff.reset()
                    async for msg in ws:
                        if msg.type != aiohttp.WSMsgType.TEXT:
                            continue
                        snap = self._parse_orderbook_frame(
                            msg.data, symbol_by_native
                        )
                        if snap is not None:
                            await on_snapshot(snap)
            except asyncio.CancelledError:
                raise
            except (aiohttp.ClientError, ConnectionResetError, OSError):
                await asyncio.sleep(backoff.next())

    def _parse_orderbook_frame(
        self, raw: str, symbol_by_native: dict[str, Symbol]
    ) -> MarketSnapshot | None:
        """Bybit frame OR ack — discriminate by `op` (ack) vs `topic` (data)."""
        try:
            payload = json.loads(raw)
            if payload.get("op") == "subscribe":
                return None  # subscription ack, not a data frame
            data = payload.get("data")
            if not isinstance(data, dict):
                return None
            native_sym = data.get("s")
            sym = symbol_by_native.get(native_sym)
            if sym is None:
                return None
            bids = data.get("b") or []
            asks = data.get("a") or []
            if not bids or not asks:
                return None
            best_bid_price, best_bid_size = bids[0]
            best_ask_price, best_ask_size = asks[0]
            return MarketSnapshot(
                exchange=self.id,
                symbol=sym,
                bid=price(str(best_bid_price)),
                ask=price(str(best_ask_price)),
                bid_size=volume(str(best_bid_size)),
                ask_size=volume(str(best_ask_size)),
                timestamp_utc=now_utc(),
            )
        except (json.JSONDecodeError, KeyError, TypeError, ValueError, IndexError):
            return None

    @requires_live_mode
    async def place_order(
        self, intent: OrderIntent, decision: RiskDecision
    ) -> OrderId:
        raise NotImplementedError(
            "BybitAdapter.place_order — Faz 7b+ (authenticated endpoints)"
        )

    @requires_live_mode
    async def cancel_order(self, order_id: OrderId) -> None:
        raise NotImplementedError("BybitAdapter.cancel_order — Faz 7b+")

    @requires_live_mode
    async def fetch_balance(self, asset: Asset) -> Volume:
        raise NotImplementedError("BybitAdapter.fetch_balance — Faz 7b+")

    @requires_live_mode
    async def fetch_fills(self, since: datetime) -> list[Fill]:
        raise NotImplementedError("BybitAdapter.fetch_fills — Faz 7b+")
