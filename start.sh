#!/usr/bin/env bash
set -euo pipefail

# Resolve the repository root directory
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

COMMAND="${1:-}"
case "$COMMAND" in
  -v|--version)
    exec env PYTHONPATH="$ROOT_DIR/src" "$ROOT_DIR/scripts/python" -m github_usage --version
    ;;
  -h|--help|"")
    cat << 'EOF'
Usage: ./start.sh <command> [options]

Commands:
  setup         Configure local secrets, options, launchd, CI, and hooks.
  report        Run a legacy one-off usage report.
  email-report  Run and send an email report.
  runs          View all currently configured scheduled runs.

Global Options:
  -h, --help    Show this help message.
  -v, --version Show the version.

For help on a specific command, run:
  ./start.sh <command> --help
EOF
    exit 0
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

    # Execute legacy report without passing empty arguments
    if [[ -n "$TOKEN" ]]; then
      if [[ ${#ARGS[@]} -eq 0 ]]; then
        exec env PYTHONPATH="$ROOT_DIR/src" "$ROOT_DIR/scripts/python" -m github_usage "$TOKEN"
      else
        exec env PYTHONPATH="$ROOT_DIR/src" "$ROOT_DIR/scripts/python" -m github_usage "$TOKEN" "${ARGS[@]}"
      fi
    else
      if [[ ${#ARGS[@]} -eq 0 ]]; then
        exec env PYTHONPATH="$ROOT_DIR/src" "$ROOT_DIR/scripts/python" -m github_usage
      else
        exec env PYTHONPATH="$ROOT_DIR/src" "$ROOT_DIR/scripts/python" -m github_usage "${ARGS[@]}"
      fi
    fi
    ;;
  email-report)
    shift
    exec env PYTHONPATH="$ROOT_DIR/src" "$ROOT_DIR/scripts/python" -m github_usage email-report "$@"
    ;;
  runs)
    shift
    exec env PYTHONPATH="$ROOT_DIR/src" "$ROOT_DIR/scripts/python" -m github_usage runs "$@"
    ;;
  *)
    echo "Error: Unknown command '$COMMAND'" >&2
    echo "Run './start.sh --help' for usage." >&2
    exit 1
    ;;
esac
