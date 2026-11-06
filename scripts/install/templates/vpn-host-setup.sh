#!/bin/sh
set -eu

REMOTE_USER=@@REMOTE_USER@@
CLI_PATH=@@CLI_PATH@@
AUTHORIZED_KEY_LINE=@@AUTHORIZED_KEY_LINE@@
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
trap 'rm -f "$TEMP_SUDOERS"' EXIT HUP INT TERM
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