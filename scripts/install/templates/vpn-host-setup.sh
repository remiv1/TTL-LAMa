#!/bin/sh
set -eu

REMOTE_USER=@@REMOTE_USER@@
CLI_PATH=@@CLI_PATH@@
AUTHORIZED_KEY_LINE=@@AUTHORIZED_KEY_LINE@@
KNOWN_HOSTS_HOST=@@KNOWN_HOSTS_HOST@@
KNOWN_HOSTS_PORT=@@SSH_PORT@@
SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
WRAPPER_PATH=/usr/local/sbin/ttlama-ssh-wrapper
SUDOERS_PATH=/etc/sudoers.d/ttlama

if [ "$(id -u)" -ne 0 ]; then
    printf '%s\n' 'Run this script again with administrator privileges.' >&2
    exit 1
fi

if [ ! -x "$CLI_PATH" ]; then
    printf 'TTL-LAMa CLI is missing or not executable: %s\n' "$CLI_PATH" >&2
    exit 1
fi

if ! command -v visudo >/dev/null 2>&1; then
    printf '%s\n' 'visudo is required to validate the sudoers rule.' >&2
    exit 1
fi

TEMP_SUDOERS=$(mktemp)
TEMP_HOST_KEYS=$(mktemp)
trap 'rm -f "$TEMP_SUDOERS" "$TEMP_HOST_KEYS"' EXIT HUP INT TERM
install -m 0440 "$SCRIPT_DIR/ttlama.sudoers" "$TEMP_SUDOERS"
visudo -cf "$TEMP_SUDOERS"

if ! id "$REMOTE_USER" >/dev/null 2>&1; then
    useradd --system --user-group --create-home \
        --home-dir "/var/lib/$REMOTE_USER" --shell /bin/sh "$REMOTE_USER"
fi
passwd --lock "$REMOTE_USER" >/dev/null 2>&1 || true

USER_HOME=$(getent passwd "$REMOTE_USER" | cut -d: -f6)
if [ -z "$USER_HOME" ] || [ ! -d "$USER_HOME" ]; then
    printf '%s\n' 'Could not determine the VPN account home directory.' >&2
    exit 1
fi

SSH_DIR="$USER_HOME/.ssh"
AUTHORIZED_KEYS="$SSH_DIR/authorized_keys"
install -d -o "$REMOTE_USER" -g "$REMOTE_USER" -m 0700 "$SSH_DIR"
if [ -s "$AUTHORIZED_KEYS" ] && ! grep -Fxq -- "$AUTHORIZED_KEY_LINE" "$AUTHORIZED_KEYS"; then
    printf '%s\n' 'authorized_keys already contains unmanaged keys; no key was changed.' >&2
    exit 1
fi
if ! grep -Fxq -- "$AUTHORIZED_KEY_LINE" "$AUTHORIZED_KEYS" 2>/dev/null; then
    printf '%s\n' "$AUTHORIZED_KEY_LINE" >> "$AUTHORIZED_KEYS"
fi
chown "$REMOTE_USER:$REMOTE_USER" "$AUTHORIZED_KEYS"
chmod 0600 "$AUTHORIZED_KEYS"

install -o root -g root -m 0755 \
    "$SCRIPT_DIR/ttlama-ssh-wrapper" "$WRAPPER_PATH"
install -o root -g root -m 0440 \
    "$SCRIPT_DIR/ttlama.sudoers" "$SUDOERS_PATH"
visudo -cf "$SUDOERS_PATH"

printf 'WireGuard setup completed for account %s.\n' "$REMOTE_USER"

if command -v ssh-keyscan >/dev/null 2>&1 && command -v ssh-keygen >/dev/null 2>&1; then
    ssh-keyscan -T 5 -p "$KNOWN_HOSTS_PORT" -t ed25519 127.0.0.1 \
        > "$TEMP_HOST_KEYS" 2>/dev/null || true
    HOST_KEY=$(awk '$2 == "ssh-ed25519" { print $2 " " $3; exit }' "$TEMP_HOST_KEYS")
    HOST_KEY_FINGERPRINT=$(ssh-keygen -lf "$TEMP_HOST_KEYS" 2>/dev/null | awk 'NR == 1 { print $2 }')
    if [ -n "$HOST_KEY" ] && [ -n "$HOST_KEY_FINGERPRINT" ]; then
        if [ "$KNOWN_HOSTS_PORT" -eq 22 ]; then
            KNOWN_HOSTS_ENTRY_HOST=$KNOWN_HOSTS_HOST
        else
            KNOWN_HOSTS_ENTRY_HOST="[$KNOWN_HOSTS_HOST]:$KNOWN_HOSTS_PORT"
        fi
        printf '\nSSH ED25519 host key fingerprint (verify independently): %s\n' \
            "$HOST_KEY_FINGERPRINT"
        printf 'Add this complete entry to the application ssh_known_hosts file:\n'
        printf '%s %s\n' "$KNOWN_HOSTS_ENTRY_HOST" "$HOST_KEY"
    else
        printf '%s\n' \
            "Could not read an ED25519 SSH host key from 127.0.0.1:$KNOWN_HOSTS_PORT." \
            'Check that the SSH service listens locally on the configured port.' >&2
    fi
else
    printf '%s\n' \
        'ssh-keyscan and ssh-keygen are required to display the SSH host key entry.' >&2
fi