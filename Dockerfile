# syntax=docker/dockerfile:1.7

ARG PYTHON_IMAGE=python:3.13.5-slim-bookworm@sha256:4c2cf9917bd1cbacc5e9b07320025bdb7cdf2df7b0ceaccb55e9dd7e30987419
FROM ${PYTHON_IMAGE}

LABEL org.opencontainers.image.title="ANUBIS" \
      org.opencontainers.image.description="Local-first AI orchestration runtime" \
      org.opencontainers.image.source="local" \
      org.opencontainers.image.licenses="UNLICENSED"

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/src:/app \
    ANUBIS_ENV=production \
    ANUBIS_NETWORK=disabled \
    ANUBIS_SANDBOX=enforced

WORKDIR /app

# Fixed UID/GID make file ownership deterministic across hosts and orchestrators.
RUN groupadd --gid 10001 anubis \
    && useradd --uid 10001 --gid anubis --no-create-home --home-dir /nonexistent \
        --shell /usr/sbin/nologin anubis

COPY --chown=10001:10001 bootstrap.py pyproject.toml requirements.txt ./
COPY --chown=10001:10001 src ./src
COPY --chown=10001:10001 core ./core
COPY --chown=10001:10001 agents ./agents
COPY --chown=10001:10001 config ./config

RUN chmod -R a-w /app \
    && find /app -type d -exec chmod 0555 {} \; \
    && find /app -type f -exec chmod 0444 {} \; \
    && chmod 0555 /app/bootstrap.py

USER 10001:10001

ENTRYPOINT ["python3", "/app/bootstrap.py"]
