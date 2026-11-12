#!/bin/sh
# Install the bundled Minis Surge CLI. Credentials belong in Minis environment variables.
set -eu
SELF_DIR="$(CDPATH='' cd -- "$(dirname -- "$0")" && pwd)"
TARGET="${SURGE_CLI_LINK:-/usr/local/bin/surge-cli}"

chmod 755 "$SELF_DIR"/*.py "$SELF_DIR"/*.sh
ln -sf "$SELF_DIR/surge_cli.py" "$TARGET"

# Verify by the PATH name, not $TARGET: a link off PATH or shadowed by an older copy is a failure.
if ! SURGE_CLI_BIN=surge-cli sh "$SELF_DIR/acceptance.sh" --installed; then
  echo "Install failed: $TARGET does not resolve to $SELF_DIR/surge_cli.py" >&2
  exit 1
fi

echo "Installed: $TARGET -> $SELF_DIR/surge_cli.py"
if [ -n "${SURGE_API_KEY:-}" ]; then
  echo "SURGE_API_KEY: set"
  echo "Run: $SELF_DIR/acceptance.sh"
else
  echo "SURGE_API_KEY: missing"
  echo "Set it in Minis Settings -> Environment Variables, then run:"
  echo "  $SELF_DIR/acceptance.sh"
fi
