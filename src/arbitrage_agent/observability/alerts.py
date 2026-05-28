"""Alert sinks — email (SMTP) + Telegram (Faz 8 part 2).

The pipeline pushes operator notifications through a `Notifier`:
kill-switch engagements, hedge aborts, and (optionally) trade fills.

Design:
- **EmailNotifier** (primary) — stdlib `smtplib` run inside a thread
  executor so the blocking SMTP handshake never stalls the asyncio
  loop. No third-party dependency.
- **TelegramNotifier** (dormant) — `aiohttp` POST to the Bot API.
  Fully implemented but only built when `telegram_enabled=true`, so
  the infrastructure is ready to switch on later.
- **CompositeNotifier** fans out to every enabled channel.
- **NullNotifier** — no-op when nothing is configured (paper smoke).

Every channel is BEST-EFFORT: a send failure is logged and swallowed,
never propagated — a flaky SMTP server must not crash the trading
loop. Secrets (`smtp_password`, `telegram_bot_token`) live only in
Settings (from `.env`) and never appear in logs or runtime status.
"""

from __future__ import annotations

import asyncio
import smtplib
from email.message import EmailMessage
from typing import Protocol, runtime_checkable

import aiohttp
import structlog

from arbitrage_agent.config import Settings

_log = structlog.get_logger()

_SUBJECT_PREFIX = "[Arbitrage Agent]"


@runtime_checkable
class Notifier(Protocol):
    """Send a single operator notification. Returns True on success."""

    async def send(self, subject: str, body: str) -> bool: ...


class NullNotifier:
    """No-op sink — used when no channel is configured."""

    async def send(self, subject: str, body: str) -> bool:  # noqa: D102
        return False


class EmailNotifier:
    """SMTP email via stdlib `smtplib`, executed off-loop."""

    def __init__(
        self,
        *,
        host: str,
        port: int,
        user: str,
        password: str,
        sender: str,
        recipient: str,
        use_tls: bool,
    ) -> None:
        self._host = host
        self._port = port
        self._user = user
        self._password = password
        self._sender = sender or user
        # Support comma-separated recipient lists.
        self._recipients = [r.strip() for r in recipient.split(",") if r.strip()]
        self._use_tls = use_tls

    async def send(self, subject: str, body: str) -> bool:
        loop = asyncio.get_running_loop()
        try:
            await loop.run_in_executor(None, self._send_sync, subject, body)
            return True
        except Exception as exc:  # noqa: BLE001 — best-effort, never crash the loop
            _log.warning(
                "alert.email_failed",
                error=f"{type(exc).__name__}: {exc}",
            )
            return False

    def _send_sync(self, subject: str, body: str) -> None:
        msg = EmailMessage()
        msg["Subject"] = f"{_SUBJECT_PREFIX} {subject}"
        msg["From"] = self._sender
        msg["To"] = ", ".join(self._recipients)
        msg.set_content(body)
        with smtplib.SMTP(self._host, self._port, timeout=15) as smtp:
            if self._use_tls:
                smtp.starttls()
            if self._user:
                smtp.login(self._user, self._password)
            smtp.send_message(msg)


class TelegramNotifier:
    """Telegram Bot API sink via aiohttp. Dormant until enabled.

    `base_url` is injectable for tests; production uses the default
    Telegram endpoint."""

    def __init__(
        self,
        *,
        bot_token: str,
        chat_id: str,
        base_url: str = "https://api.telegram.org",
    ) -> None:
        self._token = bot_token
        self._chat_id = chat_id
        self._base_url = base_url.rstrip("/")

    async def send(self, subject: str, body: str) -> bool:
        url = f"{self._base_url}/bot{self._token}/sendMessage"
        text = f"*{subject}*\n{body}"
        payload = {"chat_id": self._chat_id, "text": text, "parse_mode": "Markdown"}
        try:
            timeout = aiohttp.ClientTimeout(total=15)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(url, json=payload) as resp:
                    if resp.status != 200:
                        _log.warning("alert.telegram_failed", status=resp.status)
                        return False
            return True
        except Exception as exc:  # noqa: BLE001 — best-effort
            _log.warning(
                "alert.telegram_failed",
                error=f"{type(exc).__name__}: {exc}",
            )
            return False


class CompositeNotifier:
    """Fan out to every configured channel; success = any channel sent."""

    def __init__(self, notifiers: list[Notifier]) -> None:
        self._notifiers = notifiers

    async def send(self, subject: str, body: str) -> bool:
        results = await asyncio.gather(
            *(n.send(subject, body) for n in self._notifiers),
            return_exceptions=True,
        )
        return any(r is True for r in results)


def build_notifier(settings: Settings) -> Notifier:
    """Assemble the active notifier from Settings. Returns NullNotifier
    when nothing is configured (the paper-smoke default)."""
    notifiers: list[Notifier] = []
    if settings.alert_email_enabled and settings.smtp_host and settings.smtp_to:
        notifiers.append(EmailNotifier(
            host=settings.smtp_host,
            port=settings.smtp_port,
            user=settings.smtp_user,
            password=settings.smtp_password,
            sender=settings.smtp_from,
            recipient=settings.smtp_to,
            use_tls=settings.smtp_use_tls,
        ))
    if settings.telegram_enabled and settings.telegram_bot_token and settings.telegram_chat_id:
        notifiers.append(TelegramNotifier(
            bot_token=settings.telegram_bot_token,
            chat_id=settings.telegram_chat_id,
        ))
    if not notifiers:
        return NullNotifier()
    return CompositeNotifier(notifiers)
