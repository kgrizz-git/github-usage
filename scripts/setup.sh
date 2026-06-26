#!/usr/bin/env bash
# Guided setup wizard logic. Replaced setup.sh at root, which is now start.sh setup.
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

exec env PYTHONPATH="$ROOT_DIR/src" "$ROOT_DIR/scripts/python" -m github_usage setup "$@"
