# Crypto Arbitrage Agent — container image (Faz 8 part 3).
#
# Runs the bot as a long-lived process. Pair with `restart: always`
# (docker-compose) or a systemd unit so it survives crashes. Secrets
# come from the runtime environment (.env via compose `env_file`, or
# `-e` flags) — they are NEVER baked into the image.

FROM python:3.11-slim AS base

# No .pyc, unbuffered stdout (so structlog JSON streams to `docker logs`).
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Install dependencies first (layer caching): copy only the metadata
# needed to resolve + build the wheel, then the source.
COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install --no-cache-dir .

# Run as a non-root user — the bot never needs root, and a compromised
# process should not own the container.
RUN useradd --create-home --uid 10001 botuser \
    && mkdir -p /app/logs \
    && chown -R botuser:botuser /app
USER botuser

# logs/ holds the audit chain, kill-switch, testnet evidence, runtime
# status — mount a volume here to persist across restarts.
VOLUME ["/app/logs"]

# Prometheus metrics (opt-in via METRICS_ENABLED=true).
EXPOSE 9090

# Default paper mode is safe; override EXECUTION_MODE / PIPELINE_ITERATIONS
# via env at run time. PIPELINE_ITERATIONS=0 → run forever.
CMD ["python", "-m", "arbitrage_agent"]
