FROM docker.io/library/python:3.14-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        iproute2 \
        openssh-server \
        sudo \
        wireguard-tools \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /opt/ttlama-cli

COPY cli/pyproject.toml ./
COPY cli/src/ ./src/
RUN pip install --no-cache-dir . \
    && useradd --create-home --shell /bin/sh ttl-lama \
    && printf 'ttl-lama:test-only-password\n' | chpasswd \
    && printf 'ttl-lama ALL=(root) NOPASSWD: /usr/local/bin/ttlama\n' \
        > /etc/sudoers.d/ttlama \
    && chmod 0440 /etc/sudoers.d/ttlama

COPY tests/integration/wireguard_backend/sshd_config /etc/ssh/sshd_config
COPY tests/integration/wireguard_backend/entrypoint.sh /usr/local/bin/test-backend-entrypoint
RUN chmod 0755 /usr/local/bin/test-backend-entrypoint

ENTRYPOINT ["/usr/local/bin/test-backend-entrypoint"]