#!/usr/bin/env sh
set -eu

# Script dir = Extra-Methods-Patches/zipnerf-pytorch
PATCH_ROOT=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)

# Go up to nerfstudio_custom root
ROOT_DIR=$(CDPATH= cd -- "$PATCH_ROOT/../.." && pwd)

ORIG_FILE="$ROOT_DIR/zipnerf-pytorch/extensions/cuda/setup.py"
PATCHED_FILE="$PATCH_ROOT/extensions/cuda/setup.py"
PATCH_FILE="$PATCH_ROOT/extensions/cuda/setup.py.patch"

if [ ! -f "$ORIG_FILE" ]; then
  echo "[ERROR] Original file not found:"
  echo "        $ORIG_FILE"
  exit 1
fi

if [ ! -f "$PATCHED_FILE" ]; then
  echo "[ERROR] Patched file not found:"
  echo "        $PATCHED_FILE"
  exit 1
fi

if ! command -v git >/dev/null 2>&1; then
  echo "[ERROR] git not found in PATH"
  exit 1
fi

echo "[INFO] Generating patch..."
set +e
git diff --no-index "$ORIG_FILE" "$PATCHED_FILE" > "$PATCH_FILE"
RC=$?
set -e

if [ "$RC" -eq 0 ]; then
  echo "[INFO] No differences found"
  echo "[INFO] Patch file still written:"
  echo "       $PATCH_FILE"
  exit 0
fi

if [ "$RC" -eq 1 ]; then
  echo "[OK] Patch created:"
  echo "     $PATCH_FILE"
  exit 0
fi

echo "[ERROR] git diff failed with code $RC"
rm -f "$PATCH_FILE"
exit "$RC"