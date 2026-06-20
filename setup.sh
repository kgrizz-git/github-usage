#!/usr/bin/env bash
# setup.sh — single entry point for guided github-usage configuration.
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"

exec env PYTHONPATH=src scripts/python -m github_usage setup "$@"
