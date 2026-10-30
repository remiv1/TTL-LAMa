FROM node:22-alpine AS web-assets

LABEL maintainer="rverschuur@audit-io.fr"
LABEL org.opencontainers.image.description="TTL-LAMa Docker image"
LABEL org.opencontainers.image.licenses="MIT"
LABEL org.opencontainers.image.source="https://github.com/remiv1/TTL-LAMa"
LABEL org.opencontainers.image.version="0.0.3"

WORKDIR /build

COPY package.json package-lock.json ./
RUN npm ci
COPY src/api/web/static/scss/ ./src/api/web/static/scss/
RUN mkdir -p src/api/web/static/css && npm run build

FROM python:3.14-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/opt/ttl-lama/src

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    sqlite3 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /opt/ttl-lama

COPY src/requirements.txt /opt/ttl-lama/requirements.txt
RUN pip install --no-cache-dir -r /opt/ttl-lama/requirements.txt

COPY src/ /opt/ttl-lama/src/
COPY --from=web-assets /build/src/api/web/static/css/main.css /opt/ttl-lama/src/api/web/static/css/main.css
COPY --from=web-assets /build/src/api/web/static/js/htmx.min.js /opt/ttl-lama/src/api/web/static/js/htmx.min.js
COPY --from=web-assets /build/src/api/web/static/fonts/ /opt/ttl-lama/src/api/web/static/fonts/
RUN useradd --system --create-home --home-dir /home/ttl-lama ttl-lama \
    && mkdir -p /data /etc/ttl-lama \
    && chown ttl-lama:ttl-lama /data
COPY src/config/config.yml /etc/ttl-lama/config.yml
COPY src/config/access-profiles.yml /etc/ttl-lama/access-profiles.yml

FROM base AS test

USER root
COPY tests/requirements-test.txt /opt/ttl-lama/requirements-test.txt
RUN pip install --no-cache-dir -r /opt/ttl-lama/requirements-test.txt
COPY pytest.ini /opt/ttl-lama/pytest.ini
COPY tests/ /opt/ttl-lama/tests/
USER ttl-lama
CMD ["python", "-m", "pytest", "-q", "-p", "no:cacheprovider"]

FROM base AS runtime

USER ttl-lama
ENTRYPOINT ["sh", "/opt/ttl-lama/src/entrypoint.sh"]