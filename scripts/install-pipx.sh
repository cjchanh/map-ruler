#!/usr/bin/env bash
# Install map-ruler for the current user via pipx (or pip --user fallback).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if command -v pipx >/dev/null 2>&1; then
  echo "Installing with pipx (editable + plot extras)..."
  pipx install --force --editable "$ROOT[plot]" 2>/dev/null \
    || pipx install --force --editable "$ROOT"
  echo "OK: map-ruler available as: map-ruler --help"
  map-ruler --version || true
  exit 0
fi

echo "pipx not found — falling back to pip --user editable install"
python3 -m pip install --user -e ".$([ -n "${MAP_RULER_PLOT:-1}" ] && echo '[plot]')"
echo "OK: ensure ~/.local/bin is on PATH"
python3 -m map_ruler --version || true
