#!/bin/sh
set -eu

CLI=@@CLI_PATH@@

case "${SSH_ORIGINAL_COMMAND:-}" in
    list)
        exec "$CLI" backend wg leases ls --interface all --json
        ;;
    apply)
        exec /usr/bin/sudo -n "$CLI" backend wg leases apply --lease -
        ;;
    delete)
        exec /usr/bin/sudo -n "$CLI" backend wg leases delete --lease -
        ;;
    *)
        printf '%s\n' 'Remote command rejected.' >&2
        exit 64
        ;;
esac