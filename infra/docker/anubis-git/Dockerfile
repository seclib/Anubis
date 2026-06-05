# syntax=docker/dockerfile:1.7

ARG PYTHON_IMAGE=python:3.13.5-slim-bookworm@sha256:4c2cf9917bd1cbacc5e9b07320025bdb7cdf2df7b0ceaccb55e9dd7e30987419

FROM ${PYTHON_IMAGE} AS build

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/build/app/src:/build/app

WORKDIR /build/app

COPY pyproject.toml requirements.txt ./
COPY src/anubis/architecture.py ./src/anubis/architecture.py
COPY src/anubis/events.py ./src/anubis/events.py
COPY src/anubis/types.py ./src/anubis/types.py
RUN touch ./src/anubis/__init__.py
COPY config ./config

RUN python3 -m compileall -q src config \
    && python3 - <<'PY'
from anubis.architecture import RefactorProposal
assert RefactorProposal
PY
RUN find /build/app -type d -name __pycache__ -prune -exec rm -rf {} +

FROM ${PYTHON_IMAGE} AS runtime

LABEL org.opencontainers.image.title="anubis-git" \
      org.opencontainers.image.description="ANUBIS Git workflow service image" \
      org.opencontainers.image.licenses="UNLICENSED"

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/src:/app \
    ANUBIS_ENV=production \
    ANUBIS_SERVICE=git \
    ANUBIS_NETWORK=disabled

WORKDIR /app

RUN groupadd --gid 10001 anubis \
    && useradd --uid 10001 --gid anubis --no-create-home --home-dir /nonexistent \
        --shell /usr/sbin/nologin anubis

COPY --from=build --chown=10001:10001 /build/app /app

RUN chmod -R a-w /app \
    && find /app -type d -exec chmod 0555 {} \; \
    && find /app -type f -exec chmod 0444 {} \;

USER 10001:10001

CMD ["python3", "-c", "from anubis.architecture import RefactorProposal; print('anubis-git image ready'); import time; time.sleep(31536000)"]
