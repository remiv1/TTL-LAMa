#!/bin/sh
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
REPOSITORY_ROOT=$(CDPATH= cd -- "$SCRIPT_DIR/../.." && pwd)
VERSION=${1:-${GITHUB_REF_NAME:-}}
OUTPUT_DIR=${2:-"$REPOSITORY_ROOT/dist"}

case "$VERSION" in
    ""|.*|*[!A-Za-z0-9._-]*)
        printf '%s\n' 'Usage: build-package.sh VERSION [OUTPUT_DIRECTORY]' >&2
        exit 2
        ;;
esac

case "$OUTPUT_DIR" in
    /*) ;;
    *) OUTPUT_DIR="$PWD/$OUTPUT_DIR" ;;
esac

PACKAGE_NAME="ttlama-installer-$VERSION"
ARCHIVE_NAME="$PACKAGE_NAME.tar.gz"
CHECKSUM_NAME="$ARCHIVE_NAME.sha256"
STAGING_ROOT=$(mktemp -d)
trap 'rm -rf "$STAGING_ROOT"' EXIT HUP INT TERM
PACKAGE_ROOT="$STAGING_ROOT/$PACKAGE_NAME"

mkdir -p "$OUTPUT_DIR" "$PACKAGE_ROOT/scripts/install/templates"

install -m 0755 "$SCRIPT_DIR/install.sh" "$PACKAGE_ROOT/scripts/install/install.sh"
install -m 0644 "$SCRIPT_DIR/configure.py" "$PACKAGE_ROOT/scripts/install/configure.py"
install -m 0644 "$SCRIPT_DIR/requirements.txt" "$PACKAGE_ROOT/scripts/install/requirements.txt"
install -m 0644 "$SCRIPT_DIR/PACKAGE-README.md" "$PACKAGE_ROOT/README.md"
cp -R "$SCRIPT_DIR/templates/." "$PACKAGE_ROOT/scripts/install/templates/"

for source in \
    api/logging_config.py \
    api/config/__init__.py \
    api/config/_settings_sources.py \
    api/config/c_databases.py \
    api/config/c_flask.py \
    api/config/c_password_hasher.py \
    api/config/c_profiles.py \
    api/config/global_config.py \
    scheduler/__init__.py \
    scheduler/panic.py \
    scheduler/ssh.py
do
    mkdir -p "$PACKAGE_ROOT/src/$(dirname -- "$source")"
    install -m 0644 "$REPOSITORY_ROOT/src/$source" "$PACKAGE_ROOT/src/$source"
done

tar --sort=name --mtime='@0' --owner=0 --group=0 --numeric-owner \
    -czf "$OUTPUT_DIR/$ARCHIVE_NAME" -C "$STAGING_ROOT" "$PACKAGE_NAME"
(
    cd "$OUTPUT_DIR"
    sha256sum "$ARCHIVE_NAME" > "$CHECKSUM_NAME"
)

printf 'Created %s\n' "$OUTPUT_DIR/$ARCHIVE_NAME"
printf 'Created %s\n' "$OUTPUT_DIR/$CHECKSUM_NAME"