#!/bin/sh
set -eu

exec /usr/bin/supervisord \
    -n \
    -c /opt/ttl-lama/src/supervisor/supervisord.conf