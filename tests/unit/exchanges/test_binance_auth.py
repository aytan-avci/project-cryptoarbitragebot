"""BinanceAdapter authenticated endpoints (Faz 7b).

All HTTP traffic stays offline via aiohttp's in-process test server.
Validates: HMAC-SHA256 signature correctness (S6 — stdlib only),
`canWithdraw` probe rejection (S5), `X-MBX-APIKEY` header propagation,
place_order parameter formatting, balance lookup, missing-credentials
error path.
"""

import hashlib
import hmac
from contextlib import asynccontextmanager
from decimal import Decimal

import pytest
from aiohttp import web

from arbitrage_agent.domain import (
    Asset,
    ExchangeId,
    OrderIntent,
    OrderId,
    RiskDecision,
    Symbol,
    new_opportunity_id,
    price,
    volume,
)
from arbitrage_agent.exchanges.binance import BinanceAdapter
from arbitrage_agent.exchanges.errors import (
    InvalidOrder,
    PermanentFailure,
)


BTC = Symbol("BTC", "USDT")
TEST_KEY = "test-api-key"
TEST_SECRET = "test-api-secret-deadbeef"


@asynccontextmanager
async def _stub_server(handlers: dict[str, callable]):
    """Start aiohttp app exposing a handler per (METHOD, path) key."""
    app = web.Application()
    seen_method_paths = set()
    for key, handler in handlers.items():
        method, path = key.split(" ", 1)
        app.router.add_route(method, path, handler)
        seen_method_paths.add(key)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", 0)
    await site.start()
    port = site._server.sockets[0].getsockname()[1]  # type: ignore[union-attr]
    try:
        yield f"http://127.0.0.1:{port}"
    finally:
        await runner.cleanup()


def _expected_signature(query_without_signature: str) -> str:
    return hmac.new(
        TEST_SECRET.encode(), query_without_signature.encode(), hashlib.sha256
    ).hexdigest()


def _split_signature(query_string: str) -> tuple[str, str]:
    """Return (params_without_signature, signature_value)."""
    head, sep, sig = query_string.rpartition("&signature=")
    assert sep == "&signature=", f"no signature in query: {query_string!r}"
    return head, sig


def _live_env(monkeypatch):
    monkeypatch.setenv("EXECUTION_MODE", "live")


# ---- Signing correctness --------------------------------------------------

@pytest.mark.asyncio
async def test_signed_request_carries_correct_hmac(monkeypatch):
    _live_env(monkeypatch)
    received_signature = None
    received_apikey = None

    async def handler(request):
        nonlocal received_signature, received_apikey
        received_apikey = request.headers.get("X-MBX-APIKEY")
        query = request.rel_url.query_string
        params, sig = _split_signature(query)
        assert sig == _expected_signature(params)
        received_signature = sig
        return web.json_response({"canTrade": True, "canWithdraw": False, "balances": []})

    async with _stub_server({"GET /api/v3/account": handler}) as base_url:
        adapter = BinanceAdapter(
            base_url=base_url, api_key=TEST_KEY, api_secret=TEST_SECRET,
        )
        await adapter._ensure_no_withdraw_permission()
        await adapter.close()

    assert received_apikey == TEST_KEY
    assert received_signature is not None and len(received_signature) == 64


# ---- S5: canWithdraw probe ------------------------------------------------

@pytest.mark.asyncio
async def test_withdraw_permission_rejected(monkeypatch):
    _live_env(monkeypatch)

    async def handler(request):
        return web.json_response({
            "canTrade": True, "canWithdraw": True, "canDeposit": True,
            "balances": [],
        })

    async with _stub_server({"GET /api/v3/account": handler}) as base_url:
        adapter = BinanceAdapter(
            base_url=base_url, api_key=TEST_KEY, api_secret=TEST_SECRET,
        )
        with pytest.raises(PermanentFailure, match="withdraw permission"):
            await adapter._ensure_no_withdraw_permission()
        await adapter.close()


@pytest.mark.asyncio
async def test_cannot_trade_rejected(monkeypatch):
    _live_env(monkeypatch)

    async def handler(request):
        return web.json_response({
            "canTrade": False, "canWithdraw": False, "balances": [],
        })

    async with _stub_server({"GET /api/v3/account": handler}) as base_url:
        adapter = BinanceAdapter(
            base_url=base_url, api_key=TEST_KEY, api_secret=TEST_SECRET,
        )
        with pytest.raises(PermanentFailure, match="cannot trade"):
            await adapter._ensure_no_withdraw_permission()
        await adapter.close()


@pytest.mark.asyncio
async def test_probe_cached_after_success(monkeypatch):
    """Once the probe passes, subsequent auth calls should NOT re-probe."""
    _live_env(monkeypatch)
    probe_count = 0

    async def account_handler(request):
        nonlocal probe_count
        probe_count += 1
        return web.json_response({"canTrade": True, "canWithdraw": False, "balances": [
            {"asset": "USDT", "free": "1000.50"},
        ]})

    async with _stub_server({"GET /api/v3/account": account_handler}) as base_url:
        adapter = BinanceAdapter(
            base_url=base_url, api_key=TEST_KEY, api_secret=TEST_SECRET,
        )
        # First call probes; second call does NOT re-probe (uses cached result)
        bal1 = await adapter.fetch_balance(Asset("USDT"))
        bal2 = await adapter.fetch_balance(Asset("USDT"))
        await adapter.close()

    # `fetch_balance` itself hits /api/v3/account once per call (no caching of
    # balance), plus the very first call's probe. So 3 hits total: probe + 2 fetch.
    # Confirm probe was NOT called separately on the second fetch_balance.
    assert probe_count == 3
    assert bal1 == Decimal("1000.50")
    assert bal2 == Decimal("1000.50")


# ---- place_order ----------------------------------------------------------

def _approved_decision(opp_id: str = None) -> RiskDecision:
    return RiskDecision(
        opportunity_id=opp_id or new_opportunity_id(),
        approved=True, reason="all checks passed",
    )


def _buy_intent() -> OrderIntent:
    return OrderIntent(
        exchange=ExchangeId("binance"), symbol=BTC, side="buy",
        quantity=volume("0.001"), limit_price=price("60000"),
    )


@pytest.mark.asyncio
async def test_place_order_sends_correct_params(monkeypatch):
    _live_env(monkeypatch)
    captured = {}

    async def account_handler(request):
        return web.json_response({"canTrade": True, "canWithdraw": False, "balances": []})

    async def order_handler(request):
        query = request.rel_url.query_string
        params, sig = _split_signature(query)
        assert sig == _expected_signature(params)
        # Parse the params into a dict for assertion
        from urllib.parse import parse_qs
        captured.update({k: v[0] for k, v in parse_qs(params).items()})
        return web.json_response({"orderId": 42, "clientOrderId": captured.get("newClientOrderId")})

    async with _stub_server({
        "GET /api/v3/account": account_handler,
        "POST /api/v3/order": order_handler,
    }) as base_url:
        adapter = BinanceAdapter(
            base_url=base_url, api_key=TEST_KEY, api_secret=TEST_SECRET,
        )
        intent = _buy_intent()
        decision = _approved_decision()
        oid = await adapter.place_order(intent, decision)
        await adapter.close()

    assert captured["symbol"] == "BTCUSDT"
    assert captured["side"] == "BUY"
    assert captured["type"] == "LIMIT"
    assert captured["timeInForce"] == "GTC"
    assert captured["quantity"] == "0.001"
    assert captured["price"] == "60000"
    assert captured["newClientOrderId"] == decision.opportunity_id
    assert oid == "42"


@pytest.mark.asyncio
async def test_place_order_refuses_unapproved_decision_at_adapter(monkeypatch):
    """Defence-in-depth — adapter rejects even if execution.engine bug
    let an unapproved decision through."""
    _live_env(monkeypatch)
    adapter = BinanceAdapter(
        api_key=TEST_KEY, api_secret=TEST_SECRET,
    )
    bad_decision = RiskDecision(
        opportunity_id=new_opportunity_id(), approved=False, reason="no",
    )
    with pytest.raises(InvalidOrder, match="approved decision"):
        await adapter.place_order(_buy_intent(), bad_decision)


@pytest.mark.asyncio
async def test_place_order_blocks_when_withdraw_enabled(monkeypatch):
    _live_env(monkeypatch)

    async def account_handler(request):
        return web.json_response({"canTrade": True, "canWithdraw": True, "balances": []})

    async def order_handler(request):
        pytest.fail("place_order should not reach POST /order when canWithdraw=true")

    async with _stub_server({
        "GET /api/v3/account": account_handler,
        "POST /api/v3/order": order_handler,
    }) as base_url:
        adapter = BinanceAdapter(
            base_url=base_url, api_key=TEST_KEY, api_secret=TEST_SECRET,
        )
        with pytest.raises(PermanentFailure):
            await adapter.place_order(_buy_intent(), _approved_decision())
        await adapter.close()


# ---- fetch_balance --------------------------------------------------------

@pytest.mark.asyncio
async def test_fetch_balance_returns_free_qty(monkeypatch):
    _live_env(monkeypatch)

    async def handler(request):
        return web.json_response({
            "canTrade": True, "canWithdraw": False,
            "balances": [
                {"asset": "BTC", "free": "0.05", "locked": "0.001"},
                {"asset": "USDT", "free": "1500.00", "locked": "200.00"},
            ],
        })

    async with _stub_server({"GET /api/v3/account": handler}) as base_url:
        adapter = BinanceAdapter(
            base_url=base_url, api_key=TEST_KEY, api_secret=TEST_SECRET,
        )
        btc_bal = await adapter.fetch_balance(Asset("BTC"))
        usdt_bal = await adapter.fetch_balance(Asset("USDT"))
        unknown = await adapter.fetch_balance(Asset("DOGE"))
        await adapter.close()

    assert btc_bal == Decimal("0.05")
    assert usdt_bal == Decimal("1500.00")
    assert unknown == Decimal("0")


# ---- Missing credentials --------------------------------------------------

@pytest.mark.asyncio
async def test_missing_credentials_raises_invalid_order(monkeypatch):
    _live_env(monkeypatch)
    adapter = BinanceAdapter()  # no api_key / api_secret
    with pytest.raises(InvalidOrder, match="BINANCE_API_KEY"):
        await adapter.place_order(_buy_intent(), _approved_decision())


@pytest.mark.asyncio
async def test_only_key_no_secret_also_raises(monkeypatch):
    _live_env(monkeypatch)
    adapter = BinanceAdapter(api_key="just-key", api_secret=None)
    with pytest.raises(InvalidOrder):
        await adapter.place_order(_buy_intent(), _approved_decision())


# ---- cancel_order ---------------------------------------------------------

@pytest.mark.asyncio
async def test_cancel_order_uses_client_order_id(monkeypatch):
    _live_env(monkeypatch)
    captured = {}

    async def account_handler(request):
        return web.json_response({"canTrade": True, "canWithdraw": False, "balances": []})

    async def cancel_handler(request):
        query = request.rel_url.query_string
        params, sig = _split_signature(query)
        assert sig == _expected_signature(params)
        from urllib.parse import parse_qs
        captured.update({k: v[0] for k, v in parse_qs(params).items()})
        return web.json_response({"status": "CANCELED"})

    async with _stub_server({
        "GET /api/v3/account": account_handler,
        "DELETE /api/v3/order": cancel_handler,
    }) as base_url:
        adapter = BinanceAdapter(
            base_url=base_url, api_key=TEST_KEY, api_secret=TEST_SECRET,
        )
        await adapter.cancel_order(OrderId("opp-id-12345"))
        await adapter.close()

    assert captured["origClientOrderId"] == "opp-id-12345"


# ---- S7: testnet evidence recording (Faz 7g-d) ----------------------------


@pytest.mark.asyncio
async def test_testnet_url_records_evidence_on_successful_probe(
    monkeypatch, tmp_path,
):
    """Faz 7g-d — when the adapter's base_url indicates testnet, a
    successful S5 probe must stamp `logs/testnet_evidence.json` so the
    S7 mainnet gate later sees recorded probation days."""
    from arbitrage_agent.risk.testnet_evidence import load

    monkeypatch.chdir(tmp_path)
    _live_env(monkeypatch)

    async def account_handler(request):
        return web.json_response({
            "canTrade": True, "canWithdraw": False, "balances": [],
        })

    async with _stub_server({"GET /api/v3/account": account_handler}) as base:
        adapter = BinanceAdapter(
            base_url=base, api_key=TEST_KEY, api_secret=TEST_SECRET,
        )
        # Force testnet semantics for this test without rerouting HTTP —
        # network still hits the in-process stub, but `_is_testnet()`
        # returns True so the recorder fires.
        monkeypatch.setattr(adapter, "_is_testnet", lambda: True)
        await adapter._ensure_no_withdraw_permission()
        await adapter.close()

    ev = load(tmp_path / "logs" / "testnet_evidence.json")
    assert ev.first_seen_utc is not None
    assert "binance-testnet" in ev.venues


@pytest.mark.asyncio
async def test_mainnet_url_does_not_record_evidence(monkeypatch, tmp_path):
    """Mainnet probe success must NOT stamp testnet evidence —
    otherwise the gate becomes self-fulfilling."""
    from arbitrage_agent.risk.testnet_evidence import load

    monkeypatch.chdir(tmp_path)
    _live_env(monkeypatch)

    async def account_handler(request):
        return web.json_response({
            "canTrade": True, "canWithdraw": False, "balances": [],
        })

    async with _stub_server({"GET /api/v3/account": account_handler}) as base_url:
        adapter = BinanceAdapter(
            base_url=base_url,  # 127.0.0.1 — does NOT contain 'testnet'
            api_key=TEST_KEY, api_secret=TEST_SECRET,
        )
        await adapter._ensure_no_withdraw_permission()
        await adapter.close()

    ev = load(tmp_path / "logs" / "testnet_evidence.json")
    assert ev.first_seen_utc is None

