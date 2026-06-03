# syntax=docker/dockerfile:1.7

ARG ML_REQUIREMENTS=requirements/ml.txt

FROM python:3.13-slim AS wheel-builder

ARG ML_REQUIREMENTS

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /build

RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential gcc \
    && rm -rf /var/lib/apt/lists/*

COPY requirements ./requirements
RUN python -m pip install --upgrade pip wheel \
    && python -m pip wheel --wheel-dir /wheels -r "${ML_REQUIREMENTS}"


FROM python:3.13-slim AS runtime

ARG ML_REQUIREMENTS

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONPATH=/opt/anubis \
    ANUBIS_ENV=production \
    ANUBIS_HEALTH_HOST=0.0.0.0 \
    ANUBIS_HEALTH_PORT=8081

WORKDIR /opt/anubis

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates tini \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --shell /usr/sbin/nologin anubis

COPY --from=wheel-builder /wheels /wheels
COPY requirements ./requirements
RUN python -m pip install --no-cache-dir --no-index --find-links=/wheels -r "${ML_REQUIREMENTS}" \
    && rm -rf /wheels /root/.cache/pip

COPY anubis/distributed ./anubis/distributed
COPY anubis/__init__.py ./anubis/__init__.py
COPY backend/rag ./backend/rag
COPY memory ./memory
COPY storage ./storage

RUN mkdir -p /var/lib/anubis /var/log/anubis \
    && chown -R anubis:anubis /opt/anubis /var/lib/anubis /var/log/anubis

USER anubis

EXPOSE 8081

HEALTHCHECK --interval=15s --timeout=3s --start-period=20s --retries=5 \
  CMD python -c "import sys; sys.exit(0)"

ENTRYPOINT ["tini", "--"]
CMD ["python", "-c", "import time; print('anubis ml runtime ready', flush=True); time.sleep(10**9)"]
