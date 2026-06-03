# syntax=docker/dockerfile:1.7

FROM python:3.13-slim AS wheel-builder

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
    && python -m pip wheel --wheel-dir /wheels -r requirements/prod.txt


FROM python:3.13-slim AS runtime

ARG USER_ID=1000
ARG GROUP_ID=1000

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    APP_HOME=/app/anubis-agent \
    WORKSPACE_DIR=/workspace \
    WORKSPACE_ROOT=/workspace \
    PYTHONPATH=/app/anubis-agent \
    PROJECT_ROOT=/workspace \
    HOME=/tmp \
    TMPDIR=/tmp

WORKDIR ${APP_HOME}

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates git tini \
    && rm -rf /var/lib/apt/lists/*

COPY --from=wheel-builder /wheels /wheels
COPY requirements ./requirements
RUN python -m pip install --no-cache-dir --no-index --find-links=/wheels -r requirements/prod.txt \
    && rm -rf /wheels /root/.cache/pip

COPY anubis ./anubis
COPY api ./api
COPY app ./app
COPY backend ./backend
COPY cli ./cli
COPY core ./core
COPY crawler ./crawler
COPY executor ./executor
COPY intelligence ./intelligence
COPY knowledge ./knowledge
COPY llm ./llm
COPY memory ./memory
COPY monitoring ./monitoring
COPY rag ./rag
COPY retrieval ./retrieval
COPY runtime ./runtime
COPY services ./services
COPY skills ./skills
COPY storage ./storage
COPY tools ./tools
COPY workers ./workers
COPY config.py main.py anubis_cli.py ./
COPY docker ./docker

RUN groupadd --gid ${GROUP_ID} anubis \
    && useradd --uid ${USER_ID} --gid ${GROUP_ID} --no-create-home --shell /usr/sbin/nologin anubis \
    && mkdir -p ${WORKSPACE_DIR} \
    && chmod +x ${APP_HOME}/docker/entrypoint.sh \
    && chown -R anubis:anubis ${APP_HOME} ${WORKSPACE_DIR}

USER anubis

WORKDIR ${WORKSPACE_DIR}

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD python -c "import json, urllib.request; response = urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=3); payload = json.loads(response.read().decode()); raise SystemExit(0 if payload.get('status') == 'ok' else 1)"

ENTRYPOINT ["tini", "--", "/app/anubis-agent/docker/entrypoint.sh"]
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
