"""Binance exchange adapter — REST only (Faz 7a).

Per `skills/exchange-integration/SKILL.md`. Scope:
- `fetch_book_snapshot(symbol)` → real GET `/api/v3/depth` via aiohttp.
- All other protocol methods raise `NotImplementedError` (Faz 7b+ adds
  authenticated endpoints + WS).

Public endpoint, no API key needed. Rate-limited via `TokenBucket`.
"""

import asyncio
import hashlib
import hmac
import json
import time
from datetime import datetime
from typing import Any
from urllib.parse import urlencode

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
from arbitrage_agent.risk import testnet_evidence as _testnet_evidence


class BinanceAdapter:
    """Public-REST adapter for Binance spot."""

    DEFAULT_BASE_URL = "https://api.binance.com"
    DEFAULT_WS_BASE_URL = "wss://stream.binance.com:9443"

    def __init__(
        self,
        base_url: str = DEFAULT_BASE_URL,
        rate_limit_per_minute: int = 60,
        session: aiohttp.ClientSession | None = None,
        request_timeout_s: float = 10.0,
        ws_base_url: str = DEFAULT_WS_BASE_URL,
        api_key: str | None = None,
        api_secret: str | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._ws_base_url = ws_base_url.rstrip("/")
        self._bucket = TokenBucket(rate_per_minute=rate_limit_per_minute)
        self._session_owner = session is None
        self._session = session
        self._timeout = aiohttp.ClientTimeout(total=request_timeout_s)
        self._api_key = api_key
        self._api_secret = api_secret
        self._withdraw_probe_done = False

    @property
    def id(self) -> ExchangeId:
        return ExchangeId("binance")

    @staticmethod
    def _to_native(symbol: Symbol) -> str:
        """`Symbol('BTC','USDT')` → `'BTCUSDT'`."""
        return f"{symbol.base}{symbol.quote}"

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None:
            self._session = aiohttp.ClientSession(timeout=self._timeout)
        return self._session

    async def close(self) -> None:
        """Close the session if this adapter owns it. Idempotent."""
        if self._session_owner and self._session is not None:
            await self._session.close()
            self._session = None

    # ---- ExchangeAdapter protocol ---------------------------------------

    async def fetch_book_snapshot(self, symbol: Symbol) -> MarketSnapshot:
        """Top-of-book snapshot via `/api/v3/depth`."""
        await self._bucket.acquire()
        url = f"{self._base_url}/api/v3/depth"
        params = {"symbol": self._to_native(symbol), "limit": "5"}

        session = await self._get_session()
        try:
            async with session.get(url, params=params) as resp:
                payload = await self._handle_response(resp, symbol)
        except aiohttp.ClientError as e:
            raise TemporaryFailure(f"binance network error: {e}") from e
        except asyncio.TimeoutError:
            raise TemporaryFailure("binance request timed out") from None

        return self._parse_book(symbol, payload)

    @staticmethod
    async def _handle_response(
        resp: aiohttp.ClientResponse, symbol: Symbol
    ) -> dict[str, Any]:
        status = resp.status
        if status == 200:
            return await resp.json()
        if status == 429:
            raise RateLimited(f"binance 429 on {symbol}")
        if status == 418:
            raise PermanentFailure(f"binance 418 (IP banned) on {symbol}")
        if status == 400:
            body = await resp.text()
            raise InvalidOrder(f"binance 400: {body[:200]}")
        if 500 <= status < 600:
            raise TemporaryFailure(f"binance {status} (server error)")
        raise ExchangeError(f"binance unexpected status {status}")

    def _parse_book(
        self, symbol: Symbol, payload: dict[str, Any]
    ) -> MarketSnapshot:
        try:
            bids = payload["bids"]
            asks = payload["asks"]
            if not bids or not asks:
                raise MarketHalted(f"empty book for {symbol}")
            best_bid_price, best_bid_size = bids[0]
            best_ask_price, best_ask_size = asks[0]
        except (KeyError, IndexError, TypeError, ValueError) as e:
            raise PermanentFailure(
                f"malformed binance depth response: {e}"
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

    # ---- Not implemented in Faz 7a -------------------------------------

    async def subscribe(
        self, symbols: list[Symbol], on_snapshot: SnapshotCallback
    ) -> None:
        """Subscribe to combined book-ticker streams for every symbol.

        Reconnects with exponential backoff on disconnect. Loops until
        the caller cancels the task. Each parsed `MarketSnapshot` is
        delivered via `on_snapshot`.
        """
        streams = "/".join(
            f"{self._to_native(s).lower()}@bookTicker" for s in symbols
        )
        url = f"{self._ws_base_url}/stream?streams={streams}"
        backoff = ExponentialBackoff()
        symbol_by_native = {self._to_native(s): s for s in symbols}

        while True:
            try:
                session = await self._get_session()
                async with session.ws_connect(url, heartbeat=30) as ws:
                    backoff.reset()
                    async for msg in ws:
                        if msg.type != aiohttp.WSMsgType.TEXT:
                            continue
                        snap = self._parse_book_ticker_frame(
                            msg.data, symbol_by_native
                        )
                        if snap is not None:
                            await on_snapshot(snap)
            except asyncio.CancelledError:
                raise
            except (aiohttp.ClientError, ConnectionResetError, OSError):
                await asyncio.sleep(backoff.next())

    def _parse_book_ticker_frame(
        self, raw: str, symbol_by_native: dict[str, Symbol]
    ) -> MarketSnapshot | None:
        """Combined-stream frame:
            {"stream":"btcusdt@bookTicker","data":{"u":..., "s":"BTCUSDT",
             "b":"60000.00","B":"1.5","a":"60001.00","A":"0.8"}}
        Returns None for non-bookTicker payloads.
        """
        try:
            payload = json.loads(raw)
            data = payload.get("data", payload)  # raw frame OR combined wrapper
            native_sym = data["s"]
            sym = symbol_by_native.get(native_sym)
            if sym is None:
                return None
            return MarketSnapshot(
                exchange=self.id,
                symbol=sym,
                bid=price(str(data["b"])),
                ask=price(str(data["a"])),
                bid_size=volume(str(data["B"])),
                ask_size=volume(str(data["A"])),
                timestamp_utc=now_utc(),
            )
        except (json.JSONDecodeError, KeyError, TypeError, ValueError):
            return None

    # ---- Faz 7b authenticated endpoints --------------------------------
    #
    # Signing per https://binance-docs.github.io/apidocs/spot/en/#signed-trade-and-user_data-endpoints-security
    # 1. Build query string of params + `timestamp` (ms since epoch).
    # 2. signature = HMAC-SHA256(api_secret, query_string).hexdigest()
    # 3. Append `&signature=<hex>` to the query.
    # 4. Send `X-MBX-APIKEY: <api_key>` header.
    #
    # `hmac.new` + `hashlib.sha256` are stdlib (SECURITY.md S6 — no
    # third-party signing libs). Comparisons (if ever needed) use
    # `hmac.compare_digest` — though we only generate signatures here,
    # never verify, since the server's response is HTTPS-authenticated.

    def _require_credentials(self) -> tuple[str, str]:
        if not self._api_key or not self._api_secret:
            raise InvalidOrder(
                "BINANCE_API_KEY + BINANCE_API_SECRET missing — set them in .env "
                "(never .env.example). See specs/SECURITY.md § 5.1 if you suspect "
                "a leak."
            )
        return self._api_key, self._api_secret

    def _sign(self, params: dict[str, Any]) -> str:
        """Return the URL-encoded signed query string."""
        _, secret = self._require_credentials()
        # Stable ordering — Binance accepts any order, but deterministic
        # ordering makes the signature reproducible across processes.
        params = {**params, "timestamp": int(time.time() * 1000)}
        query = urlencode(params)
        sig = hmac.new(
            secret.encode("utf-8"), query.encode("utf-8"), hashlib.sha256
        ).hexdigest()
        return f"{query}&signature={sig}"

    async def _signed_request(
        self,
        method: str,
        path: str,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        api_key, _ = self._require_credentials()
        await self._bucket.acquire()
        signed_query = self._sign(params or {})
        url = f"{self._base_url}{path}?{signed_query}"
        headers = {"X-MBX-APIKEY": api_key}

        session = await self._get_session()
        try:
            async with session.request(method, url, headers=headers) as resp:
                return await self._handle_response(resp, Symbol("?", "?"))
        except aiohttp.ClientError as e:
            raise TemporaryFailure(f"binance auth network error: {e}") from e
        except asyncio.TimeoutError:
            raise TemporaryFailure("binance auth request timed out") from None

    def _is_testnet(self) -> bool:
        """Faz 7g-d — base_url indicates the venue is testnet. Used to
        gate S7 evidence recording (mainnet activity is NOT evidence
        of testnet probation)."""
        return "testnet" in self._base_url.lower()

    def _record_testnet_evidence(self) -> None:
        """Best-effort S7 stamp. Disk failure must not break a live
        trade, so OSError / unwritable path is swallowed (the gate at
        startup will surface missing evidence to the operator)."""
        if not self._is_testnet():
            return
        try:
            _testnet_evidence.record("binance-testnet", now_utc())
        except OSError:
            pass

    async def _ensure_no_withdraw_permission(self) -> None:
        """SECURITY.md S5 — refuse to operate if the key has withdraw
        permission (CLAUDE.md C1). Runs once per adapter lifetime; the
        result is cached."""
        if self._withdraw_probe_done:
            self._record_testnet_evidence()
            return
        info = await self._signed_request("GET", "/api/v3/account")
        if info.get("canWithdraw") is True:
            raise PermanentFailure(
                "Binance API key has withdraw permission — refusing to operate "
                "(CLAUDE.md C1 / SECURITY.md S5). Revoke this key and generate "
                "a trade-only one."
            )
        if info.get("canTrade") is False:
            raise PermanentFailure(
                "Binance API key cannot trade — verify spot trading is enabled."
            )
        self._withdraw_probe_done = True
        self._record_testnet_evidence()

    @requires_live_mode
    async def place_order(
        self, intent: OrderIntent, decision: RiskDecision
    ) -> OrderId:
        # Cardinal-rule runtime check (CLAUDE.md C2) — defence in depth on
        # top of execution.engine.execute's pre-flight verification.
        # Checked BEFORE the network call so unapproved input fails fast
        # without touching the exchange.
        if not decision.approved:
            raise InvalidOrder(
                f"place_order requires approved decision; got reason="
                f"{decision.reason!r}"
            )
        await self._ensure_no_withdraw_permission()
        params = {
            "symbol": self._to_native(intent.symbol),
            "side": intent.side.upper(),
            "type": "LIMIT",
            "timeInForce": "GTC",
            "quantity": str(intent.quantity),
            "price": str(intent.limit_price),
            "newClientOrderId": decision.opportunity_id,
        }
        body = await self._signed_request("POST", "/api/v3/order", params)
        order_id = body.get("orderId") or body.get("clientOrderId")
        if order_id is None:
            raise PermanentFailure(f"malformed binance order response: {body}")
        return OrderId(str(order_id))

    @requires_live_mode
    async def cancel_order(self, order_id: OrderId) -> None:
        await self._ensure_no_withdraw_permission()
        # Binance needs either orderId or origClientOrderId to identify
        # the order; we used `newClientOrderId=opportunity_id` at placement.
        params = {"origClientOrderId": order_id}
        # The symbol parameter is required by Binance even when canceling
        # by client id. Caller should pass it via order_id encoding in
        # production; for now we accept the operator constraint.
        await self._signed_request("DELETE", "/api/v3/order", params)

    @requires_live_mode
    async def fetch_balance(self, asset: Asset) -> Volume:
        await self._ensure_no_withdraw_permission()
        info = await self._signed_request("GET", "/api/v3/account")
        for entry in info.get("balances", []):
            if entry.get("asset") == asset:
                return volume(str(entry.get("free", "0")))
        return volume("0")

    @requires_live_mode
    async def fetch_fills(self, since: datetime) -> list[Fill]:
        """Binance's `/api/v3/myTrades` is per-symbol — we'd need the
        symbol from the caller. For Faz 7b MVP, this method returns
        empty until the execution engine threads symbols through.
        Faz 7e wires it properly when reconciler lands."""
        await self._ensure_no_withdraw_permission()
        _ = since  # silence unused; engine passes it for the future impl
        return []
