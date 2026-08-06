#!/usr/bin/env bash
set -euo pipefail

# Resolve the repository root directory
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

show_help() {
  cat << 'EOF'
Usage: ./start.sh [<command>] [options]

Default (interactive terminal): launches the Textual TUI via github-usage.

Commands (CLI shortcuts — no --cli required):
  setup         Configure local secrets, options, launchd, CI, and hooks.
  report        Run a one-off local full usage report.
  email-report  Run and send an email report.
  runs          View all currently configured scheduled runs.
  runs-diff     Check for drift between local workflows and the remote default branch.

Global Options:
  --cli         Command-line mode (bash menu when no subcommand, or forward to github-usage).
  -h, --help    Show this help message.
  -v, --version Show the version.

For help on a specific command, run:
  ./start.sh <command> --help
EOF
}

show_menu() {
  while true; do
    echo ""
    echo "github-usage (CLI menu — use ./start.sh without --cli for the TUI)"
    echo ""
    echo "  1) Run Guided Setup (setup)"
    echo "  2) Run Local Full Report (report)"
    echo "  3) Run and Send Email Report (email-report)"
    echo "  4) View Scheduled Runs (profiles, launchd + GitHub cron)"
    echo "  5) Check Scheduled Runs Drift (runs-diff)"
    echo "  6) Show Standard Help (--help)"
    echo "  7) Exit (q)"
    echo ""
    read -r choice || exit 0
    case "$choice" in
      1)
        exec "$ROOT_DIR/start.sh" setup
        ;;
      2)
        exec "$ROOT_DIR/start.sh" report
        ;;
      3)
        exec "$ROOT_DIR/start.sh" email-report
        ;;
      4)
        exec "$ROOT_DIR/start.sh" runs
        ;;
      5)
        exec "$ROOT_DIR/start.sh" runs-diff
        ;;
      6)
        show_help
        exit 0
        ;;
      7|q|Q)
        exit 0
        ;;
      *)
        echo "Invalid choice. Enter 1-7 or q."
        ;;
    esac
  done
}

run_github_usage() {
  exec env PYTHONPATH="$ROOT_DIR/src" "$ROOT_DIR/scripts/python" -m github_usage "$@"
}

# Parse --cli from arguments
CLI_MODE=0
FILTERED=()
for arg in "$@"; do
  if [[ "$arg" == "--cli" ]]; then
    CLI_MODE=1
  else
    FILTERED+=("$arg")
  fi
done
set -- "${FILTERED[@]}"

COMMAND="${1:-}"
case "$COMMAND" in
  -v|--version)
    run_github_usage --version
    ;;
  -h|--help)
    show_help
    exit 0
    ;;
  "")
    if [[ "$CLI_MODE" == "1" ]]; then
      if [[ -t 0 || "${FORCE_INTERACTIVE:-}" == "1" ]]; then
        show_menu
      else
        show_help
        exit 0
      fi
    elif [[ -t 0 ]]; then
      run_github_usage
    else
      show_help
      exit 0
    fi
    ;;
  setup)
    shift
    exec "$ROOT_DIR/scripts/setup.sh" "$@"
    ;;
  report)
    shift
    TOKEN=""
    ARGS=()
    while [[ $# -gt 0 ]]; do
      case "$1" in
        --token)
          if [[ -z "${2:-}" || "${2:-}" == "--" || "${2:-}" == -* ]]; then
            echo "Error: --token requires a non-empty value that does not start with '-'" >&2
            exit 1
          fi
          TOKEN="$2"
          shift 2
          ;;
        --token=*)
          val="${1#*=}"
          if [[ -z "$val" || "$val" == "--" || "$val" == -* ]]; then
            echo "Error: --token value cannot be empty, start with '-' or be '--'" >&2
            exit 1
          fi
          TOKEN="$val"
          shift
          ;;
        --month|--month=*)
          echo "Error: --month YYYY-MM is unsupported; GitHub billing API does not support date-range filtering (see docs/api-discovery-month.md)" >&2
          exit 1
          ;;
        --)
          ARGS+=("$1")
          shift
          ARGS+=("$@")
          break
          ;;
        *)
          ARGS+=("$1")
          shift
          ;;
      esac
    done

    if [[ -n "$TOKEN" ]]; then
      if [[ ${#ARGS[@]} -eq 0 ]]; then
        GITHUB_USAGE_CLI=1 run_github_usage "$TOKEN"
      else
        GITHUB_USAGE_CLI=1 run_github_usage "$TOKEN" "${ARGS[@]}"
      fi
    else
      if [[ ${#ARGS[@]} -eq 0 ]]; then
        GITHUB_USAGE_CLI=1 run_github_usage
      else
        GITHUB_USAGE_CLI=1 run_github_usage "${ARGS[@]}"
      fi
    fi
    ;;
  email-report)
    shift
    run_github_usage email-report "$@"
    ;;
  runs)
    shift
    run_github_usage runs "$@"
    ;;
  runs-diff)
    shift
    run_github_usage runs --diff "$@"
    ;;
  *)
    if [[ "$CLI_MODE" == "1" ]]; then
      run_github_usage --cli "$COMMAND" "${@:2}"
    else
      echo "Error: Unknown command '$COMMAND'" >&2
      echo "Run './start.sh --help' for usage." >&2
      exit 1
    fi
    ;;
esac
