FROM python:3.11-slim

ARG USER_ID=1000
ARG GROUP_ID=1000

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    APP_HOME=/opt/anubis-agent \
    WORKSPACE_DIR=/workspace \
    PYTHONPATH=/opt/anubis-agent \
    PROJECT_ROOT=/workspace \
    HOME=/tmp \
    TMPDIR=/tmp

WORKDIR ${APP_HOME}

COPY requirements.txt .
RUN python -m pip install --upgrade pip \
    && python -m pip install -r requirements.txt

COPY . ${APP_HOME}

RUN groupadd --gid ${GROUP_ID} anubis \
    && useradd --uid ${USER_ID} --gid ${GROUP_ID} --no-create-home --shell /usr/sbin/nologin anubis \
    && mkdir -p ${WORKSPACE_DIR} \
    && chown -R anubis:anubis ${APP_HOME} ${WORKSPACE_DIR}

USER anubis

WORKDIR ${WORKSPACE_DIR}

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD python -c "import json, urllib.request; response = urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=3); payload = json.loads(response.read().decode()); raise SystemExit(0 if payload.get('status') == 'ok' else 1)"

ENTRYPOINT ["python", "-m", "app.main"]
CMD ["serve"]
