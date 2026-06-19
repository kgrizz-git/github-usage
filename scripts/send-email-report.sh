#!/usr/bin/env bash
# send-email-report.sh
#
# Runs `github-usage email-report` for local or launchd scheduled delivery.
# Configuration is managed by `scripts/setup` (single setup entry point).
#
# Inputs:
#   - Optional env file (default: .env.email-report in the repo root)
#   - Optional report options from .github-usage/config.toml
#   - GITHUB_TOKEN or gh auth token (resolved by the CLI)
#   - RESEND_API_KEY, REPORT_EMAIL, RESEND_FROM for live sends
#   - Extra CLI flags passed as script arguments (override config)
#
# Outputs:
#   - Sends the report email via Resend (unless --dry-run is passed)
#   - Appends run output to reports/email-report-YYYYMMDD-HHMMSS.log

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

ENV_FILE="${GITHUB_USAGE_ENV_FILE:-$ROOT_DIR/.env.email-report}"
LOG_DIR="${GITHUB_USAGE_LOG_DIR:-$ROOT_DIR/reports}"
mkdir -p "$LOG_DIR"

if [[ -f "$ENV_FILE" ]]; then
  set -a
  # shellcheck disable=SC1090
  source "$ENV_FILE"
  set +a
fi

CONFIG_ARGS=()
if [[ -f "$ROOT_DIR/.github-usage/config.toml" ]]; then
  while IFS= read -r arg; do
    CONFIG_ARGS+=("$arg")
  done < <(PYTHONPATH=src scripts/python -m github_usage setup --print-args)
fi

STAMP="$(date +%Y%m%d-%H%M%S)"
LOG_FILE="$LOG_DIR/email-report-${STAMP}.log"

{
  echo "==> send-email-report started at $(date -Iseconds)"
  PYTHONPATH=src scripts/python -m github_usage email-report "${CONFIG_ARGS[@]}" "$@"
  echo "==> send-email-report finished at $(date -Iseconds)"
} >>"$LOG_FILE" 2>&1
