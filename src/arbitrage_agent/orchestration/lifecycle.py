"""Process lifecycle — startup, graceful shutdown, signal handling.

Faz 4 skeleton; concrete handlers in Faz 6.
"""


async def startup() -> None:
    """Bring exchanges, ingestion, persistence online."""
    raise NotImplementedError("lifecycle.startup — Faz 6")


async def shutdown() -> None:
    """Drain in-flight orders, close connections, flush logs."""
    raise NotImplementedError("lifecycle.shutdown — Faz 6")
