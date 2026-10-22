FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/opt/ttl-lama/src

WORKDIR /opt/ttl-lama

COPY src/requirements.txt /opt/ttl-lama/requirements.txt
RUN pip install --no-cache-dir -r /opt/ttl-lama/requirements.txt

COPY src/ /opt/ttl-lama/src/
RUN useradd --system --create-home --home-dir /home/ttl-lama ttl-lama \
    && mkdir -p /data /etc/ttl-lama \
    && chown ttl-lama:ttl-lama /data
COPY src/config/config.yml /etc/ttl-lama/config.yml
COPY src/config/access-profiles.yml /etc/ttl-lama/access-profiles.yml

FROM base AS test

USER root
COPY src/requirements-test.txt /opt/ttl-lama/requirements-test.txt
RUN pip install --no-cache-dir -r /opt/ttl-lama/requirements-test.txt
COPY pytest.ini /opt/ttl-lama/pytest.ini
COPY tests/ /opt/ttl-lama/tests/
USER ttl-lama
CMD ["python", "-m", "pytest", "-q", "-p", "no:cacheprovider"]

FROM base AS runtime

USER ttl-lama
EXPOSE 8080
ENTRYPOINT ["sh", "/opt/ttl-lama/src/entrypoint.sh"]