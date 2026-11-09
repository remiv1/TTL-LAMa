#!/bin/sh
set -eu

CLI=@@CLI_PATH@@

case "${SSH_ORIGINAL_COMMAND:-}" in
    'sudo -n ttlama backend wg leases ls --interface all --json')
        exec /usr/bin/sudo -n "$CLI" backend wg leases ls --interface all --json
        ;;
    'sudo -n ttlama backend wg leases get --lease - --json')
        exec /usr/bin/sudo -n "$CLI" backend wg leases get --lease - --json
        ;;
    'sudo -n ttlama backend wg leases apply --lease -')
        exec /usr/bin/sudo -n "$CLI" backend wg leases apply --lease -
        ;;
    'sudo -n ttlama backend wg leases delete --lease -')
        exec /usr/bin/sudo -n "$CLI" backend wg leases delete --lease -
        ;;
    *)
        printf '%s\n' 'Remote command rejected.' >&2
        exit 64
        ;;
esac