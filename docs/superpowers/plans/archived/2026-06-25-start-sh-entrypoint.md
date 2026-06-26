# Plan: start.sh entrypoint

> **Status:** COMPLETE
>
> This plan has been implemented.

**Date:** 2026-06-25

## Objective

Create a root-level `start.sh` entrypoint that unifies guided setup, one-off legacy report execution, and scheduled/dry-run email reports into a single discoverable script, then move the existing `setup.sh` into `scripts/` so `start.sh` becomes the primary user-facing entrypoint.

The `start.sh` script should let users:

1. **Set up** — delegate to `setup.sh` (which moves to `scripts/`).
2. **Run a legacy report** — invoke the legacy report format with inline flags, including support for `--token` (mapping it to the required positional argument).
3. **Run an email report** — invoke the `email-report` subcommand with standard flags.

## Motivation

- `setup.sh` is for configuration only; users who want a quick one-off report or want to run `email-report` manually need to remember the python invocation or use the legacy `github-usage` wrapper, which requires installing the package.
- A single `./start.sh` at the repo root is easier to discover and provides a single command for all modes. This implements the task outlined in `TO_DO.md` (line 23).
- Once `start.sh` exists, `setup.sh` logically belongs in `scripts/` since it is no longer the single root entrypoint.

## Proposed Implementation

### 1. Move `setup.sh` to `scripts/setup.sh`

- Relocate the root `setup.sh` using `git mv setup.sh scripts/setup.sh` to preserve file history.
- Relocate its relative path resolution for the root directory (adjusting for it now being one level down inside `scripts/`):
  - Change the line from `ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"` to `ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"`.
- Ensure the full file contents after the move look like this. *(The PYTHONPATH and `scripts/python` arguments must use absolute `$ROOT_DIR`-prefixed paths because the file now lives in `scripts/` and relative paths would resolve against the wrong directory when invoked from outside the repo root.)*

  ```bash
  #!/usr/bin/env bash
  # Guided setup wizard logic. Replaced setup.sh at root, which is now start.sh setup.
  set -euo pipefail

  ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
  cd "$ROOT_DIR"

  exec env PYTHONPATH="$ROOT_DIR/src" "$ROOT_DIR/scripts/python" -m github_usage setup "$@"
  ```

**Mitigating Naming Collision Risk (`scripts/setup` vs `scripts/setup.sh`):**
To prevent developer confusion, we will add clear explanatory headers. *(Shell tab-completion will surface both `scripts/setup` and `scripts/setup.sh`; this is expected and accepted. The comment headers are the intended disambiguation.)*
- `scripts/setup` header:
  `# Legacy shim to preserve backward compatibility. Forwards to scripts/setup.sh.`
- `scripts/setup.sh` header:
  `# Guided setup wizard logic. Replaced setup.sh at root, which is now start.sh setup.`

### 2. Update `scripts/setup` Legacy Shim

The legacy shim `scripts/setup` should be updated to forward to the new location (Note: the shim intentionally does not `cd` to `$ROOT_DIR`; it only resolves the path and delegates execution. This is consistent with the current shim behavior):
```bash
#!/usr/bin/env bash
# DEPRECATED: legacy shim. Use "./start.sh setup" instead.
# Kept temporarily for callers that still invoke "scripts/setup" directly.
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
exec "$ROOT_DIR/scripts/setup.sh" "$@"
```

*Note: After this change, `scripts/setup` should be removed once external callers migrate. Track removal as a follow-up TODO in a later release.*

### 3. Create `start.sh` at the Repository Root

A new executable bash script `start.sh` with three modes of operation. It will begin with `#!/usr/bin/env bash` and `set -euo pipefail` for safety and consistency.

**Global Options & Top-Level Dispatcher:**
Global options like `-h/--help` and `-v/--version` are handled first, followed by routing to the specific mode.

```bash
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
    # Token parsing loop and report execution handled here
    ;;
  email-report)
    shift
    exec env PYTHONPATH="$ROOT_DIR/src" "$ROOT_DIR/scripts/python" -m github_usage email-report "$@"
    ;;
  *)
    echo "Error: Unknown command '$COMMAND'" >&2
    echo "Run './start.sh --help' for usage." >&2
    exit 1
    ;;
esac
```

*(Note: `-v` and `--version` are global options handled at the top-level. Running `./start.sh email-report --version` is not supported, as subcommands handle their own parsing.)*

**Mode: Setup**
```bash
./start.sh setup [setup-options...]
```
Delegates directly to `scripts/setup.sh`. All `setup-options` are forwarded verbatim.

**Mode: Legacy Report**
```bash
./start.sh report [options]
```
Invokes the Python module with the legacy report subcommand, wrapping commonly-needed CLI flags. Example invocations:

```bash
./start.sh report                                # interactive (prompts for export format)
./start.sh report --token ghp_xxx                # non-interactive with a provided token
./start.sh report --export csv --output report.csv   # quick one-liner
```

**Underlying behavior when flags are omitted:**
*(These describe the legacy Python CLI's behavior, not wrapper-added defaults. The wrapper does not synthesize prompts or values.)*

| Scenario | Behavior |
|----------|----------|
| No token flag, `GITHUB_TOKEN` unset | Prompt interactively (or error in non-TTY) |
| `--export` omitted | Prompt in TTY, else no export |
| `--output` omitted with `--export` | Auto-generate filename |
| `--output` omitted without `--export` | Output to stdout (legacy behavior) |

**Flag mapping** — `start.sh report` flags map directly to `github-usage` CLI legacy flags:

| `start.sh` flag | Maps to | Notes |
|-----------------|---------|-------|
| `--token TOKEN` | `github-usage TOKEN` | Passed as positional arg |
| `--export FORMAT` | `--export FORMAT` | Same choices: csv/xlsx/pdf/json/text/none |
| `--output PATH` | `--output PATH` | |
| `--json` | `--json` | |
| `--no-interactive` | `--no-interactive` | |
| `--dry-run` | `--dry-run` | |
| `-h`, `--help` | `-h`, `--help` | Printed via Python's legacy help (Not intercepted by the wrapper; falls through to `ARGS`) |
| `--version` | `--version` | Printed via Python's legacy version |
| `--timeout SECONDS` | `--timeout SECONDS` | |
| `--max-retries N` | `--max-retries N` | |

Note: Email-report specific flags (e.g. `--include-consumers`, `--max-repos`, etc.) are not recognized by the legacy parser. They are not supported in `report` mode.

If a user tries to pass `--month` or `--month=YYYY-MM`, the wrapper will intercept it and fail early with a clear message: `"Error: --month YYYY-MM is unsupported; GitHub billing API does not support date-range filtering (see docs/api-discovery-month.md)"`.

**Argument Parsing for `--token` & `--` separator:**
In Bash, to safely extract the `--token` flag, check for errors, respect the `--` option separator, and translate options into positional arguments for the legacy CLI, `start.sh` will parse:
```bash
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
```

*Bare Token Positionals:* If a user passes a bare token as a positional argument (e.g. `./start.sh report ghp_xxx`), the wrapper will forward it verbatim in `ARGS`, and the Python CLI's `_split_optional_token` will process it natively. *(Also verify the legacy Python CLI's `_split_optional_token` correctly processes a positional token when `--` appears afterward (e.g., `github-usage TOKEN -- --export json`). Add this case to the smoke tests.)*

**Mode: Email Report**
```bash
./start.sh email-report [options]
```
Delegates directly to:
```bash
exec env PYTHONPATH="$ROOT_DIR/src" "$ROOT_DIR/scripts/python" -m github_usage email-report "$@"
```

Note: `start.sh email-report` is a parallel command for manual user interaction (including dry-runs). Automated runs (macOS LaunchAgent, GitHub Actions workflow, `setup --verify`) continue to use the direct script `scripts/send-email-report.sh` to keep automated runner dependencies decoupled. The root `github-usage` Python wrapper remains untouched for backward-compatible packaging.

*`start.sh email-report` does not auto-load `.env.email-report` or `.github-usage/config.toml`. For config-aware runs, use `scripts/send-email-report.sh` or export the env vars manually before calling `start.sh email-report`.*

### 4. Update Documentation and Code References

The list of files to update with the new setup paths and `./start.sh` entry points:

| File | Change |
|------|--------|
| `README.md` | Document `./start.sh` as the primary entrypoint (with a prominent mode example early on); remove all references to `setup.sh` (do not mention `scripts/setup.sh` to keep user focus entirely on `start.sh`). |
| `CHANGELOG.md` | Leave the prior `Changed` note verbatim. Add a *new* `Changed` entry under `[Unreleased]` reading approximately: *"**Unified entrypoint via `start.sh`:** Added a root-level `start.sh` wrapper that dispatches to `setup`, `report`, and `email-report` modes, and moved the guided setup script from `./setup.sh` to `scripts/setup.sh` (reached via `start.sh setup`). The previous root entrypoint remains as a thin `scripts/setup` shim."* Also add a corresponding `Added` line: *"**`start.sh` entrypoint script:** Root-level unified CLI for setup, one-off legacy reports, and email-report runs."* |
| `TO_DO.md` | Remove the `start.sh` item once implemented. |
| `AGENTS.md` | Update the entrypoint rule: "Use `./start.sh` as the primary entry point for setup, one-off reports, and email-report configuration." (keeps the existing scope of the rule but updates the entrypoint). |
| `src/github_usage/cli.py` | Update the `HELP` string's "Setup" section to reference `./start.sh setup`. (Note: Keep edits minimal as the file approaches the 500-line soft limit). |
| `src/github_usage/setup_config.py` | Update file docstring mentioning `./setup.sh`. |
| `src/github_usage/setup_wizard.py` | Update file docstring and the printed completion message referencing `./setup.sh`. Note: `setup_wizard.py` is over the 500-line soft limit (tracked in `TO_DO.md`). This PR only edits two strings and does not regress the size; the planned module split remains a separate task. |
| `src/github_usage/setup_workflow.py` | Update file docstring mentioning `./setup.sh`. |
| `tests/test_setup_wizard.py` | Update file docstring referencing `./setup.sh`. |
| `launchd/com.github.github-usage.email-report.plist` | Update references to `./setup.sh` in XML comments, acknowledging the wrapper exists for human use without misleading readers into thinking launchd invokes it. |
| `.env.email-report.example` | Update comment references. |
| `.gitignore` | Update comments if they reference `setup.sh`. |
| `scripts/send-email-report.sh` | Update comments referencing `setup.sh`. |
| `scripts/docs-check` | <ul><li>Replace `test -x setup.sh` with `test -x start.sh` and `test -x scripts/setup.sh`. Keep the `test -x scripts/setup` check.</li><li>Update the `README.md` grep check pattern to match `./start.sh`.</li><li>Replace `python3 -m github_usage` with `scripts/python -m github_usage` for consistency.</li><li>Verify that `start.sh` is executable.</li></ul> |
| `scripts/smoke` | <ul><li>Replace `./setup.sh --help` with `./start.sh setup --help`.</li><li>Verify `./start.sh --help`, `./start.sh report --help`, and `./start.sh email-report --help`.</li><li>Add a test for `./start.sh --version` (asserting `github-usage`).</li><li>Assert `scripts/setup --help` works from a subdirectory.</li><li>Preserve the legacy `scripts/setup --help` check.</li><li>Consistently use `scripts/python` instead of `.venv/bin/python`.</li></ul> |
| `scripts/check` | <ul><li>Add `test -x start.sh` and `./start.sh --help >/dev/null` verification step.</li><li>Ensure `scripts/python` is used instead of `.venv/bin/python` for consistency with smoke test updates.</li></ul> |

### 5. Verification

- Run `scripts/check` to ensure no Python changes break tests and `start.sh` is executable.
- Run `scripts/smoke` to verify the CLI still starts correctly and subcommands return expected responses.
- Run `scripts/docs-check` to verify README and entrypoint references are consistent.
- Test manually:
  - `./start.sh --help` — prints usage.
  - `./start.sh setup --help` — delegates to `scripts/setup.sh --help`.
  - `./start.sh report --help` — prints report flags.
  - `./start.sh email-report --help` — prints email report flags.
  - `./start.sh report --export json --no-interactive` — runs a one-off report with JSON output.
  - `./start.sh report ghp_fake --no-interactive --dry-run` — verifies bare token positional parsing.
  - `./start.sh report --month 2025-01` — verifies early-exit with the unsupported error message.
  - `./start.sh setup --status` — delegates correctly.
  - `scripts/setup --status` — the legacy shim still works after the move.

## Implementation Order

### Phase 1: Move `setup.sh` to `scripts/`

- [ ] Move `setup.sh` to `scripts/setup.sh` using `git mv`, ensure it remains executable (`chmod +x`), add clarifying header, and run `git add --chmod=+x scripts/setup.sh`.
- [ ] Update `scripts/setup.sh` path resolution to repository root (`/..`).
- [ ] Update the `scripts/setup` shim to forward to `scripts/setup.sh` and add clarifying header.

### Phase 2: Create `start.sh`

> [!NOTE]
> Intermediate commits in this PR will have broken doc references. Complete all three phases before the PR is marked ready for review, or squash-merge so broken intermediate states are never in `main`.

- [ ] Write `start.sh` at the repo root, executable (`chmod +x`), and run `git add --chmod=+x start.sh` to persist the executable bit.
- [ ] Implement subcommand dispatch: `setup` delegates, `report` handles arguments/flags, `email-report` forwards directly.
- [ ] Implement robust argument parsing loop for `--token`, `--month` interception, and `--` separator in `report` subcommand.
- [ ] Implement `--version` and `-v` delegation to Python.
- [ ] Handle `--help` and empty arguments (usage hint) at both levels.

### Phase 3: Update Docs and References

- [ ] Run a scoped search: `rg -n "setup\.sh" -g '!docs/superpowers/plans/**' -g '!backups/**' -g '!tmp/**' -g '!.git/**' -g '!reports/**' -g '!__pycache__/**' .` to locate any missed references. Note that archived plans under `docs/superpowers/plans/archived/` are intentionally left as-is.
- [ ] Verify `.github/workflows/email-report.yml.template` and `docs/api-discovery-month.md` are also clean (no live references expected). If found, update them. (Also verify `GEMINI.md` needs no update since it defers to `AGENTS.md` and contains no `setup.sh` reference).
- [ ] Update `README.md` references.
- [ ] Update `AGENTS.md` repository expectations.
- [ ] Update Python files: `src/github_usage/cli.py` (HELP string), `setup_config.py`, `setup_wizard.py` (completion message & docstring), `setup_workflow.py`.
- [ ] Update test files and configuration comments (`tests/test_setup_wizard.py`, `.env.email-report.example`, `.gitignore`, `launchd/com.github.github-usage.email-report.plist`, `scripts/send-email-report.sh`).
- [ ] Update `scripts/docs-check` patterns, `scripts/smoke` checks, and `scripts/check`.
- [ ] Update `CHANGELOG.md` and `TO_DO.md`.

### Phase 4: Verification

- [ ] Run `scripts/check`.
- [ ] Run `scripts/smoke`. Keep the existing `python -m github_usage` no-token test *and* add a parallel `./start.sh report` no-token check. Add a bare-token smoke test (`./start.sh report ghp_fake --dry-run`). Extend `scripts/smoke` (or add a `tests/test_start_sh.sh`) to exercise `start.sh` routing, `--version` (grep for `github-usage`), `--month` rejection, and empty token failures. Ensure existing Python invocations in smoke (and `scripts/check`) use `scripts/python`.
- [ ] Run `scripts/docs-check`.
- [ ] Run `shellcheck start.sh scripts/setup.sh scripts/setup scripts/send-email-report.sh` if `shellcheck` is installed locally to verify shell script quality and safety.
- [ ] Manual smoke tests as described above.
- [ ] Archive this plan to `docs/superpowers/plans/archived/` once completely implemented.

## Rollback Plan

- If any regressions are identified post-merge, a single-commit `git revert` should be performed (this correctly covers `scripts/smoke` and `scripts/docs-check` atomically). After `git revert`, run `git status` to confirm `setup.sh` is restored at the root and `scripts/setup.sh` is removed. If the rename wasn't cleanly inverted, manually `git mv scripts/setup.sh setup.sh` and amend the revert commit.
- During development, `scripts/setup` (the legacy shim) must be kept working to ensure backward compatibility and a safe fallback mechanism.
- Checks in `docs-check` and `smoke` scripts will test both `./start.sh` and the `scripts/setup` shim to prevent regression on either path.

## Deferred / Out of Scope

- PowerShell equivalents — tracked separately in `TO_DO.md` (Configuration & Setup section). A new deferred task for `start.ps1` will be added there.
- Interactive menu mode (not needed; flag-driven approach is simpler and CI-friendly).
- `--month` flag — remains deferred per existing decision.
- Root `github-usage` compatibility wrapper (Python script) — remains untouched.
- `scripts/prune-backups` and `scripts/security` — verified unaffected.
