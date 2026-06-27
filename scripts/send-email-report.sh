#!/usr/bin/env bash
# send-email-report.sh
#
# Runs `github-usage email-report` for local or launchd scheduled delivery.
# Configuration is managed by `./start.sh setup` (single setup entry point).
#
# Inputs:
#   - Optional --profile NAME (default: default) selects a report profile
#   - Optional env file (default: .env.email-report in the repo root)
#   - Report options expanded from .github-usage/config.toml via setup --print-args
#   - GITHUB_TOKEN or gh auth token (resolved by the CLI)
#   - RESEND_API_KEY, REPORT_EMAIL, RESEND_FROM for live sends
#   - Extra CLI flags passed as script arguments (override config)
#
# Outputs:
#   - Sends the report email via Resend (unless --dry-run is passed)
#   - Appends run output to reports/email-report-<profile>-YYYYMMDD-HHMMSS.log

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

PROFILE="default"
REMAINING_ARGS=()
while [[ $# -gt 0 ]]; do
  case "$1" in
    --profile)
      if [[ $# -lt 2 ]]; then
        echo "Error: --profile requires a profile name." >&2
        exit 1
      fi
      PROFILE="$2"
      shift 2
      ;;
    --profile=*)
      PROFILE="${1#--profile=}"
      shift
      ;;
    *)
      REMAINING_ARGS+=("$1")
      shift
      ;;
  esac
done
set -- "${REMAINING_ARGS[@]}"

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
  done < <(PYTHONPATH=src scripts/python -m github_usage setup --print-args --profile "$PROFILE")
fi

STAMP="$(date +%Y%m%d-%H%M%S)"
LOG_FILE="$LOG_DIR/email-report-${PROFILE}-${STAMP}.log"

{
  echo "==> send-email-report started at $(date -Iseconds) profile=$PROFILE"
  PYTHONPATH=src scripts/python -m github_usage email-report "${CONFIG_ARGS[@]}" "$@"
  echo "==> send-email-report finished at $(date -Iseconds)"
} >>"$LOG_FILE" 2>&1
