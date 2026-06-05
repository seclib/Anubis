# syntax=docker/dockerfile:1.7

ARG PYTHON_IMAGE=python:3.13.5-slim-bookworm@sha256:4c2cf9917bd1cbacc5e9b07320025bdb7cdf2df7b0ceaccb55e9dd7e30987419

FROM ${PYTHON_IMAGE} AS build

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/build/app/src:/build/app

WORKDIR /build/app

COPY pyproject.toml requirements.txt ./
COPY core/memory ./core/memory
COPY core/__init__.py ./core/__init__.py
COPY src/anubis/memory.py ./src/anubis/memory.py
COPY src/anubis/types.py ./src/anubis/types.py
RUN touch ./src/anubis/__init__.py

RUN python3 -m compileall -q core src \
    && python3 - <<'PY'
from core.memory import MemoryManager
from anubis.memory import SharedMemory, MemoryStoragePolicy
assert MemoryManager and SharedMemory and MemoryStoragePolicy
PY
RUN find /build/app -type d -name __pycache__ -prune -exec rm -rf {} +

FROM ${PYTHON_IMAGE} AS runtime

LABEL org.opencontainers.image.title="anubis-memory" \
      org.opencontainers.image.description="ANUBIS memory wrapper service image for durable memory/Qdrant integration" \
      org.opencontainers.image.licenses="UNLICENSED"

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/src:/app \
    ANUBIS_ENV=production \
    ANUBIS_SERVICE=memory \
    ANUBIS_NETWORK=internal

WORKDIR /app

RUN groupadd --gid 10001 anubis \
    && useradd --uid 10001 --gid anubis --no-create-home --home-dir /nonexistent \
        --shell /usr/sbin/nologin anubis

COPY --from=build --chown=10001:10001 /build/app /app

RUN chmod -R a-w /app \
    && find /app -type d -exec chmod 0555 {} \; \
    && find /app -type f -exec chmod 0444 {} \;

USER 10001:10001

CMD ["python3", "-c", "from core.memory import MemoryManager; print('anubis-memory image ready'); import time; time.sleep(31536000)"]
