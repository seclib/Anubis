# syntax=docker/dockerfile:1.7

ARG PYTHON_IMAGE=python:3.13.5-slim-bookworm@sha256:4c2cf9917bd1cbacc5e9b07320025bdb7cdf2df7b0ceaccb55e9dd7e30987419

FROM ${PYTHON_IMAGE} AS build

WORKDIR /build/ui

RUN cat > index.html <<'HTML'
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>ANUBIS UI</title>
</head>
<body>
  <main>
    <h1>ANUBIS UI service image</h1>
    <p>The repository does not yet contain a frontend application. This image is a production
    static-serving placeholder for the future workspace UI artifact.</p>
  </main>
</body>
</html>
HTML

FROM ${PYTHON_IMAGE} AS runtime

LABEL org.opencontainers.image.title="anubis-ui" \
      org.opencontainers.image.description="ANUBIS workspace UI static service image" \
      org.opencontainers.image.licenses="UNLICENSED"

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    ANUBIS_ENV=production \
    ANUBIS_SERVICE=ui

WORKDIR /app

RUN groupadd --gid 10001 anubis \
    && useradd --uid 10001 --gid anubis --no-create-home --home-dir /nonexistent \
        --shell /usr/sbin/nologin anubis

COPY --from=build --chown=10001:10001 /build/ui /app/ui

RUN chmod -R a-w /app \
    && find /app -type d -exec chmod 0555 {} \; \
    && find /app -type f -exec chmod 0444 {} \;

USER 10001:10001

EXPOSE 8080

CMD ["python3", "-m", "http.server", "8080", "--directory", "/app/ui"]
