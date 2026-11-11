#!/bin/sh
# Compatibility entry for read-only provenance inspection; no implicit prepare/apply.
set -eu
SELF_DIR="$(CDPATH='' cd -- "$(dirname -- "$0")" && pwd)"
exec python3 -B "$SELF_DIR/update_upstream.py" "$@"
