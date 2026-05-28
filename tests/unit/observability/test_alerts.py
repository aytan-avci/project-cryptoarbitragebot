"""Notifier sinks — email / telegram / composite / null (Faz 8 part 2)."""

import asyncio

import pytest
from aiohttp import web

from arbitrage_agent.config import Settings
from arbitrage_agent.observability.alerts import (
    CompositeNotifier,
    EmailNotifier,
    NullNotifier,
    TelegramNotifier,
    build_notifier,
)


# ---- build_notifier selection ---------------------------------------------


def _settings(**overrides) -> Settings:
    import os
    for k in list(os.environ):
        if k.startswith(("ALERT_", "SMTP_", "TELEGRAM_")):
            os.environ.pop(k, None)
    return Settings(**overrides)


def test_build_notifier_null_when_nothing_enabled():
    assert isinstance(build_notifier(_settings()), NullNotifier)


def test_build_notifier_email_only():
    n = build_notifier(_settings(
        alert_email_enabled=True, smtp_host="smtp.test", smtp_to="me@test",
    ))
    assert isinstance(n, CompositeNotifier)
    assert len(n._notifiers) == 1
    assert isinstance(n._notifiers[0], EmailNotifier)


def test_build_notifier_skips_email_without_recipient():
    # enabled + host but NO recipient → not built (would fail at send).
    n = build_notifier(_settings(alert_email_enabled=True, smtp_host="smtp.test"))
    assert isinstance(n, NullNotifier)


def test_build_notifier_telegram_dormant_until_enabled():
    # token + chat present but telegram_enabled=False → not built.
    n = build_notifier(_settings(
        telegram_bot_token="123:abc", telegram_chat_id="42",
    ))
    assert isinstance(n, NullNotifier)


def test_build_notifier_both_channels():
    n = build_notifier(_settings(
        alert_email_enabled=True, smtp_host="smtp.test", smtp_to="me@test",
        telegram_enabled=True, telegram_bot_token="123:abc", telegram_chat_id="42",
    ))
    assert isinstance(n, CompositeNotifier)
    assert len(n._notifiers) == 2


# ---- NullNotifier ---------------------------------------------------------


def test_null_notifier_returns_false():
    assert asyncio.run(NullNotifier().send("x", "y")) is False


# ---- EmailNotifier (mock smtplib) -----------------------------------------


def test_email_notifier_builds_message_and_sends(monkeypatch):
    sent = {}

    class FakeSMTP:
        def __init__(self, host, port, timeout=None):
            sent["host"] = host
            sent["port"] = port

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def starttls(self):
            sent["tls"] = True

        def login(self, user, password):
            sent["login"] = (user, password)

        def send_message(self, msg):
            sent["subject"] = msg["Subject"]
            sent["to"] = msg["To"]
            sent["from"] = msg["From"]
            sent["body"] = msg.get_content()

    monkeypatch.setattr("smtplib.SMTP", FakeSMTP)

    n = EmailNotifier(
        host="smtp.test", port=587, user="u@test", password="secret",
        sender="from@test", recipient="a@test, b@test", use_tls=True,
    )
    ok = asyncio.run(n.send("Test subject", "line1\nline2"))
    assert ok is True
    assert sent["host"] == "smtp.test"
    assert sent["tls"] is True
    assert sent["login"] == ("u@test", "secret")
    assert sent["subject"] == "[Arbitrage Agent] Test subject"
    assert sent["to"] == "a@test, b@test"
    assert "line1" in sent["body"]


def test_email_notifier_swallows_failure(monkeypatch):
    class ExplodingSMTP:
        def __init__(self, *a, **k):
            raise OSError("connection refused")

    monkeypatch.setattr("smtplib.SMTP", ExplodingSMTP)
    n = EmailNotifier(
        host="smtp.test", port=587, user="", password="",
        sender="from@test", recipient="a@test", use_tls=False,
    )
    # Must NOT raise — best-effort. Returns False.
    assert asyncio.run(n.send("s", "b")) is False


# ---- TelegramNotifier (in-process stub server) ----------------------------


@pytest.mark.asyncio
async def test_telegram_notifier_posts_payload():
    captured = {}

    async def handler(request):
        captured["token_path"] = request.match_info["token"]
        captured["json"] = await request.json()
        return web.json_response({"ok": True})

    app = web.Application()
    app.router.add_post("/bot{token}/sendMessage", handler)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", 0)
    await site.start()
    port = site._server.sockets[0].getsockname()[1]

    try:
        n = TelegramNotifier(
            bot_token="TESTTOKEN", chat_id="999",
            base_url=f"http://127.0.0.1:{port}",
        )
        ok = await n.send("Hello", "world")
        assert ok is True
        assert captured["token_path"] == "TESTTOKEN"
        assert captured["json"]["chat_id"] == "999"
        assert "Hello" in captured["json"]["text"]
        assert "world" in captured["json"]["text"]
    finally:
        await runner.cleanup()


@pytest.mark.asyncio
async def test_telegram_notifier_returns_false_on_non_200():
    async def handler(request):
        return web.json_response({"ok": False}, status=400)

    app = web.Application()
    app.router.add_post("/bot{token}/sendMessage", handler)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", 0)
    await site.start()
    port = site._server.sockets[0].getsockname()[1]
    try:
        n = TelegramNotifier(
            bot_token="T", chat_id="1", base_url=f"http://127.0.0.1:{port}",
        )
        assert await n.send("s", "b") is False
    finally:
        await runner.cleanup()


# ---- CompositeNotifier ----------------------------------------------------


def test_composite_success_if_any_channel_succeeds():
    class Yes:
        async def send(self, s, b):
            return True

    class No:
        async def send(self, s, b):
            return False

    c = CompositeNotifier([No(), Yes()])
    assert asyncio.run(c.send("s", "b")) is True


def test_composite_false_if_all_fail():
    class No:
        async def send(self, s, b):
            return False

    c = CompositeNotifier([No(), No()])
    assert asyncio.run(c.send("s", "b")) is False


def test_composite_swallows_channel_exception():
    class Boom:
        async def send(self, s, b):
            raise RuntimeError("boom")

    class Yes:
        async def send(self, s, b):
            return True

    c = CompositeNotifier([Boom(), Yes()])
    # gather(return_exceptions=True) → boom captured, Yes wins.
    assert asyncio.run(c.send("s", "b")) is True
