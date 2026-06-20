# Plan: Move Setup Entrypoint
**Date:** 2026-06-20

**Done:** 2026-06-20 — Created root `./setup.sh` entrypoint and replaced `scripts/setup` with a thin backward-compat shim; updated README (7), AGENTS.md, CHANGELOG, code docstrings (cli.py, setup_config.py, setup_wizard.py, tests), `.env.email-report.example`, `.gitignore`, `scripts/send-email-report.sh`, plist template, `scripts/docs-check`, and `scripts/smoke`. `scripts/check` (200 tests) and `scripts/docs-check` pass. No deviations from the plan.

## Objective
Move the `scripts/setup` entrypoint to the root of the repository (as `./setup.sh`) for easier user discovery, while maintaining backward compatibility so that existing references, CI configurations, and tests are not broken.

*Note on filename:* We are using `setup.sh` rather than `setup` to avoid ambiguity and collision issues with older `setuptools` tooling, IDEs, or plugins that look for `setup` or adjacent files like `setup.cfg`.

## Proposed Implementation

### 1. Create the Root Entrypoint
- [x] Create a new executable script `setup.sh` in the root repository folder and ensure it is executable (`chmod +x setup.sh && git add setup.sh`).
- [x] Its contents will establish the repo root and invoke the python module, passing any arguments directly to the `setup` subcommand:
  ```bash
  #!/usr/bin/env bash
  # setup.sh — single entry point for guided github-usage configuration.
  set -euo pipefail
  ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
  cd "$ROOT_DIR"
  exec env PYTHONPATH=src scripts/python -m github_usage setup "$@"
  ```

### 2. Maintain Backward Compatibility
- [x] Replace the existing `scripts/setup` script with a wrapper that forwards to the new root script, ensuring users or scripts accustomed to calling `scripts/setup` are not broken. Ensure it remains executable.
  ```bash
  #!/usr/bin/env bash
  # Legacy entrypoint: forwards to the root setup script
  ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
  exec "$ROOT_DIR/setup.sh" "$@"
  ```
  *(Note: The shim intentionally delegates all behavior, including `--help`, to the underlying script without printing a legacy warning notice, keeping output clean.)*

### 3. Update Code and Documentation References
Replace mentions of `scripts/setup` with `./setup.sh` or `setup.sh` in the following files:
- [x] **Documentation**:
  - `README.md`: Replace all 7 occurrences (at lines 60, 75, 76, 107, 209, 222, 271) to ensure the documentation clearly leads with `./setup.sh`.
  - `AGENTS.md`: Update the rule mentioning the entry point from `scripts/setup` to `./setup.sh`.
  - `CHANGELOG.md`: Leave historical references (like line 14) as-is, but add a new "Unreleased" section entry noting the migration to `./setup.sh`.
  - `docs/`: Execute a blanket search (`rg -n "scripts/setup" docs/`) to ensure no other references exist outside this plan.
- [x] **Code Comments & Docstrings**:
  - `src/github_usage/cli.py`: Update the CLI help text block. (Careful: do not rewrite `github-usage setup [options]`).
  - `src/github_usage/setup_config.py`: Update the module docstring.
  - `src/github_usage/setup_wizard.py`: Update the module docstring and completion print statements.
  - `tests/test_setup_wizard.py`: Update the module docstring to reference `./setup.sh`.
  - `.env.email-report.example`: Update the header comment at line 2.
  - `.gitignore`: Update the comment above the `.github-usage` exclusion.
  - `scripts/send-email-report.sh`: Update the header comment at line 5 to reflect the new entrypoint and remove the false "(single setup entry point)" parenthetical about the scripts dir. Confirm no other `scripts/setup` references exist in the shell body.
  - `launchd/com.github.github-usage.email-report.plist`: Update comments in the plist template at lines 4 and 8.
  - `scripts/setup`: The shim's header comment must be explicitly updated to indicate it is a legacy wrapper.

### 4. Update Repo Checks and Tests
- [x] **`scripts/docs-check`**:
  - Update the grep pattern to be permissive yet meaningful: `grep -qE '(^|[[:space:]])\./setup\.sh([[:space:]]|$)' README.md`
  - Add `test -x setup.sh` to ensure the new root script is executable.
  - Keep `test -x scripts/setup` to ensure the backward compatibility shim is still executable.
- [x] **`scripts/smoke`**:
  - Explicitly add smoke test commands to run `./setup.sh --help` and `scripts/setup --help` to verify both entrypoints work.
  - *Note:* Do not run `./setup.sh` without arguments in the smoke test, as it requires an interactive TTY and would fail in CI.

### 5. Plan Archival
- [x] **Archive**: After the implementation lands, move this plan to `docs/superpowers/plans/archived/`.

## Verification
- Run `scripts/docs-check` to verify the README and entrypoints align and are both executable.
- Run `./setup.sh --status` and `./setup.sh --verify` to ensure the new root entrypoint works correctly.
- Run `scripts/setup --status` to ensure the backward compatibility wrapper forwards correctly.
- Run `scripts/smoke` to test the new `--help` execution paths added in step 4. Check that quoting handles spaces correctly.
- Run `scripts/check` to ensure no broader issues or python errors were introduced.
- Run a final workspace search (`rg -n "scripts/setup" .`) to ensure only the legacy shim and intentionally retained historical mentions remain.
