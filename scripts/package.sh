#!/bin/sh
# The packaging gate. We submit a zip, not a clone, so this proves the zip.
#
# 1. Build the submission zip from tracked files only (git archive of HEAD).
#    An untracked file on this disk cannot rescue the build: that is exactly
#    the failure that hid the fixture evidence bundle until Day 2.
# 2. Refuse it if it is 50 MB or larger.
# 3. Extract it into an empty temporary directory and run the build gate there.
#
# Usage: scripts/package.sh [output.zip]      (default: dist/agent-readiness-audit.zip)
set -eu

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
PY=${PYTHON:-}
if [ -z "$PY" ]; then
  if command -v python3 >/dev/null 2>&1; then PY=python3; else PY=python; fi
fi
OUT=${1:-"$ROOT/dist/agent-readiness-audit.zip"}
LIMIT_BYTES=$((50 * 1024 * 1024))

cd "$ROOT"
if [ -n "$(git status --porcelain --untracked-files=no)" ]; then
  echo "note: tracked files have uncommitted changes; the zip is built from HEAD and does not include them" >&2
fi

mkdir -p "$(dirname "$OUT")"
rm -f "$OUT"
git archive --format=zip --prefix=agent-readiness-audit/ -o "$OUT" HEAD
SIZE=$(wc -c < "$OUT" | tr -d ' ')
if [ "$SIZE" -ge "$LIMIT_BYTES" ]; then
  echo "FAIL: $OUT is $SIZE bytes; the submission limit is 50 MB ($LIMIT_BYTES bytes)" >&2
  exit 1
fi

TMP=$(mktemp -d 2>/dev/null || mktemp -d -t ara-package)
trap 'rm -rf "$TMP"' EXIT INT TERM
"$PY" -m zipfile -e "$OUT" "$TMP"
echo "extracted to a clean directory; running the build gate there"
PYTHONDONTWRITEBYTECODE=1 "$PY" "$TMP/agent-readiness-audit/scripts/check.py"

echo "OK: $OUT is $SIZE bytes (limit $LIMIT_BYTES) and passes the build gate from a clean extraction"
