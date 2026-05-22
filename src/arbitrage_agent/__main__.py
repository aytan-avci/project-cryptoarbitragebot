"""Entry point for `python -m arbitrage_agent`.

Faz 6: real config (pydantic-settings) + structured JSON logging
(structlog) + a paper-trade pipeline that detects → risks → executes
opportunities for `Settings.pipeline_iterations` iterations, writing an
audit trail to the JSON-lines decision log.
"""

import asyncio
import sys

import structlog

from arbitrage_agent import __version__
from arbitrage_agent.config import Settings
from arbitrage_agent.observability import configure_logging
from arbitrage_agent.orchestration import pipeline


def main() -> int:
    settings = Settings()
    configure_logging(level=settings.log_level)
    log = structlog.get_logger()
    log.info(
        "agent.start",
        version=__version__,
        mode=settings.execution_mode,
        iterations=settings.pipeline_iterations,
    )

    summary = asyncio.run(pipeline.run(settings))

    log.info("agent.complete", **summary)
    return 0


if __name__ == "__main__":
    sys.exit(main())
