"""Logging setup tests — JSON output, secret redaction, idempotency."""

import json

import structlog

from arbitrage_agent.observability.logging_setup import configure_logging


def test_emits_one_json_line_per_event(capsys):
    configure_logging(level="INFO")
    log = structlog.get_logger()
    log.info("test.event", key="value")
    out = capsys.readouterr().out.strip()
    assert "\n" not in out  # exactly one line
    payload = json.loads(out)
    assert payload["event"] == "test.event"
    assert payload["key"] == "value"
    assert payload["level"] == "info"
    assert "timestamp" in payload


def test_redacts_known_secret_keys(capsys):
    configure_logging(level="INFO")
    log = structlog.get_logger()
    log.info(
        "auth",
        binance_api_key="sk-real-key",
        api_secret="hunter2",
        token="abc",
        username="alice",  # not a secret
    )
    payload = json.loads(capsys.readouterr().out.strip())
    assert payload["binance_api_key"] == "***"
    assert payload["api_secret"] == "***"
    assert payload["token"] == "***"
    assert payload["username"] == "alice"


def test_redacts_s2_expanded_needles(capsys):
    """SECURITY.md S2 — new needles: signature, hmac, private_key,
    bearer, auth, credential, passphrase, salt, pwd."""
    configure_logging(level="INFO")
    log = structlog.get_logger()
    log.info(
        "auth.handshake",
        signature="abc123deadbeef",
        hmac_sha256="0123456789abcdef" * 4,
        private_key="MIIEvQIBADANBgkqhkiG9w0BA…",
        bearer_token="eyJ0eXAiOi…",
        authorization="Basic dXNlcjpwYXNz",
        user_credential="bob:pa55word",
        passphrase="open-sesame",
        salt_value="randomly-generated-salt-32bytes",
        pwd="hunter3",
        public_id="visible-not-a-secret",  # negative control
    )
    payload = json.loads(capsys.readouterr().out.strip())
    for masked in (
        "signature",
        "hmac_sha256",
        "private_key",
        "bearer_token",
        "authorization",
        "user_credential",
        "passphrase",
        "salt_value",
        "pwd",
    ):
        assert payload[masked] == "***", masked
    assert payload["public_id"] == "visible-not-a-secret"


def test_redacts_byte_values(capsys):
    """SECURITY.md S2 — raw bytes are always masked regardless of key name."""
    configure_logging(level="INFO")
    log = structlog.get_logger()
    log.info(
        "raw.material",
        any_key_name=b"\x00\x01\xde\xad\xbe\xef" * 8,
        bytearray_field=bytearray(b"sensitive-bytes-payload"),
        string_field="this is just a string",  # not masked
    )
    payload = json.loads(capsys.readouterr().out.strip())
    assert payload["any_key_name"] == "***"
    assert payload["bytearray_field"] == "***"
    assert payload["string_field"] == "this is just a string"


def test_redacts_only_truthy_values(capsys):
    """Empty / None secret fields shouldn't render as '***' (no info leaked)."""
    configure_logging(level="INFO")
    log = structlog.get_logger()
    log.info("auth", api_key="", token=None)
    payload = json.loads(capsys.readouterr().out.strip())
    assert payload["api_key"] == ""
    assert payload["token"] is None


def test_level_filters(capsys):
    configure_logging(level="WARNING")
    log = structlog.get_logger()
    log.info("should.be.dropped")
    log.warning("should.appear")
    out = capsys.readouterr().out.strip()
    payloads = [json.loads(line) for line in out.splitlines() if line]
    events = [p["event"] for p in payloads]
    assert "should.be.dropped" not in events
    assert "should.appear" in events


def test_idempotent_reconfiguration():
    # Should not raise on repeated calls
    configure_logging(level="INFO")
    configure_logging(level="DEBUG")
    configure_logging(level="WARNING")
