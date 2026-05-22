"""Structured JSON logging via structlog.

After `configure_logging(level)`, every `structlog.get_logger()` emits one
JSON line per event to stdout. Two redaction processors run before the
JSON renderer:

* `_redact_secret_keys` — masks any field whose **name** contains a
  known-credential needle (SECURITY.md C6 + S2). Substring match,
  case-insensitive.
* `_redact_byte_values` — masks any field whose **value** is a `bytes`
  / `bytearray` (raw key material, HMAC digests, etc.).

Both processors are defence-in-depth for CLAUDE.md § 2 C6.
"""

import logging
from typing import Any, Final

import structlog

# Substring needles matched against the field NAME (lowercase). Any match
# masks the value. Conservative additions land here, not in a config —
# operator should not be able to silently expand or shrink this list
# (SECURITY.md S2 § "Open / Deferred Items": no operator-extensible
# needles).
_SECRET_KEY_NEEDLES: Final[frozenset[str]] = frozenset({
    # Original Faz 3 set
    "api_key",
    "api_secret",
    "password",
    "secret",
    "token",
    # Faz 7-S S2 additions (HMAC signing, auth headers, key material)
    "pwd",
    "signature",
    "hmac",
    "private_key",
    "bearer",
    "auth",
    "credential",
    "passphrase",
    "salt",
})


def _redact_secret_keys(
    _logger: Any, _method_name: str, event_dict: dict[str, Any]
) -> dict[str, Any]:
    """Replace credential-named field values with '***'. Empty / None
    values are left as-is so the absence of a key is not telegraphed as
    a present-but-masked one."""
    for key in list(event_dict.keys()):
        lower = key.lower()
        if any(needle in lower for needle in _SECRET_KEY_NEEDLES):
            if event_dict[key] not in (None, ""):
                event_dict[key] = "***"
    return event_dict


def _redact_byte_values(
    _logger: Any, _method_name: str, event_dict: dict[str, Any]
) -> dict[str, Any]:
    """Replace any raw `bytes` / `bytearray` value with '***'. Strings
    matching base64 or hex shapes are NOT redacted (would hit UUIDs,
    order ids, etc.) — those rely on the key-name needle list above."""
    for key, value in list(event_dict.items()):
        if isinstance(value, (bytes, bytearray)):
            event_dict[key] = "***"
    return event_dict


def configure_logging(level: str = "INFO") -> None:
    """Idempotent. Call once at startup."""
    level_int = getattr(logging, level.upper())
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            _redact_secret_keys,
            _redact_byte_values,
            structlog.processors.JSONRenderer(sort_keys=True),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(level_int),
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=False,
    )
