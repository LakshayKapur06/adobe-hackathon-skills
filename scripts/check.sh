#!/bin/sh
# The build gate. One command, no dependencies beyond Python 3.10+.
# Usage: scripts/check.sh [--only NAME]... [--list]
set -eu
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
PY=${PYTHON:-}
if [ -z "$PY" ]; then
  if command -v python3 >/dev/null 2>&1; then PY=python3; else PY=python; fi
fi
exec "$PY" "$ROOT/scripts/check.py" "$@"
