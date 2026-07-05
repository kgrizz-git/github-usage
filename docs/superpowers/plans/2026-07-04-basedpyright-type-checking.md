> **Status:** NEEDS REVIEW
>
> **DO NOT MERGE** until review is complete. This plan is submitted for discussion.

# Add basedpyright Static Type Checking

Add [`basedpyright`](https://docs.basedpyright.com/) (a faster, maintained fork of Microsoft pyright) as a step in `scripts/check` and a dedicated CI job to catch cross-module import/type errors before they reach `main`.

---

## Current State

- No type checker is configured. `scripts/check` runs syntax checks, unit tests, CLI smoke test, file-size limits, and backup policy — but no static type analysis.
- `.pre-commit-config.yaml` has a `stages: [pre-push]` local hook that runs `scripts/check` (tests + smoke). A pre-push type-check hook would run in the same stage.
- `.github/workflows/ci.yml` runs `scripts/check` on PR and push-to-main across Python 3.11–3.13. No separate type-check job.
- `pyproject.toml` has no `[tool.basedpyright]` section.
- `TO_DO.md` already updated to reference this plan (line 12).

## Rationale for basedpyright over pyright

- Drop-in compatible — same config keys, same CLI flags, same `# type: ignore` comments.
- Faster cold-start and incremental runs (significant for a pre-push hook).
- Active maintenance with better Python 3.12/3.13 stdlib type coverage.
- PyPI package (`pip install basedpyright`) — no Node.js dependency.

## Existing Type-Error Baseline

The codebase has never been type-checked. A first `basedpyright src` run will likely report hundreds of diagnostics. The plan handles these in two sub-phases: first establish a config baseline (with errors permitted), then fix all errors to reach zero.

## Definition of Done

- `basedpyright src tests` exits 0 with the project's configured strictness level.
- A `scripts/typecheck` wrapper exists (consistent with `scripts/check`).
- `scripts/check` runs `scripts/typecheck`, so type errors fail the pre-push hook (via the existing `run-scripts-check` hook) and local verification.
- CI runs `basedpyright src tests` in a separate `typecheck` job and fails on any error.
- basedpyright cache dir (`.basedpyright/`) is in `.gitignore`.
- The plan is archived after merge with status COMPLETE.

## Proposed Implementation

### Phase 0 — Add dev dependency and baseline config

1. Add `basedpyright>=1.30` to `[project.optional-dependencies] dev` in `pyproject.toml`. (Current latest is 1.39.9 — the minimum is a safety floor, not a pin.)
2. Add `scripts/typecheck`:
   ```bash
   #!/usr/bin/env bash
   set -euo pipefail
   ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
   cd "$ROOT_DIR"
   exec basedpyright src tests
   ```
   **Note:** `basedpyright` installs a CLI entry point, not a Python module — `python -m basedpyright` will not work (no `__main__.py`). This script uses `basedpyright` via PATH, consistent with how `scripts/format` resolves `ruff` and `black`. The dev-extras install (`pip install -e '.[dev]'`) places `basedpyright` on PATH via the venv.
   Make it executable: `chmod +x scripts/typecheck`.
   Optionally add `scripts/typecheck.ps1` (PowerShell) for Windows compatibility — see `TO_DO.md` item for Windows script parity.
3. Add `.basedpyright/` to `.gitignore` (type-checker cache directory).
4. Add a `[tool.basedpyright]` section in `pyproject.toml`:

```toml
[tool.basedpyright]
typeCheckingMode = "standard"
include = ["src", "tests"]
exclude = ["backups", ".venv"]
reportMissingImports = "error"
reportMissingTypeStubs = "none"       # too noisy until third-party stubs are added
reportUnknownMemberType = "none"      # too noisy for existing code
reportUnknownParameterType = "none"   # too noisy for existing code
reportUnknownVariableType = "none"    # too noisy for existing code
reportUntypedFunctionDecorator = "none"
reportUntypedClassDecorator = "none"
reportPrivateImportUsage = "none"     # allow _-prefixed module imports
pythonVersion = "3.11"
```

   **`exclude` note:** basedpyright does not support ruff-style `**/.*` double-star globs here; use plain paths relative to the project root. Hidden directories (`.venv`, `.git`, etc.) are excluded by default by basedpyright.

   **`extraPaths` note:** Omitted intentionally. Since the package is installed as `pip install -e .`, Python's path already includes `src`. Adding `extraPaths = ["src"]` may cause double-import confusion with the editable install. Add it back only if imports are not resolved after Phase 0.

5. Run `scripts/typecheck` to establish the baseline error count. **Phase 0 changes can be committed with or without errors** — the config is locked in here; Phase 1 is what resolves all errors to zero.

Config rationale:
- `reportMissingTypeStubs = "none"`: Third-party deps (`textual`, `openpyxl`, `fpdf2`) have no stubs. Set to `"none"` initially to avoid noise. Can be raised to `"warning"` later with individual `# type: ignore[import-untyped]` suppressions added per dependency.
- `pythonVersion = "3.11"`: The project minimum. basedpyright reports errors that would occur at this version, which is a superset of the issues it would flag for 3.12/3.13 (both backward-compatible). A single run suffices for all supported versions.

### Phase 1 — Fix or suppress all existing errors

Fix clear bugs and add `# type: ignore[code]` with a brief comment for intentional violations (e.g. dynamic attribute access on API response dicts).

Likely error categories and remediation:

| Category | Typical cause | Remediation |
|---|---|---|
| Missing imports / stub | Stdlib or third-party modules have no stubs | Add `# type: ignore[import-untyped]` or install stubs |
| Implicit `Any` | Function params / returns without annotations | Add annotations; suppressed by `reportUnknown* = "none"` |
| Incompatible return type | `-> dict \| None` but code assumes dict | Add `assert result is not None` or narrow return type |
| Dynamic attribute access | `data.get("key")` on `dict[str, Any]` | Use `TypedDict` for known shapes; `# type: ignore` for fully dynamic API responses |

After this phase, `scripts/typecheck` exits 0.

### Phase 2 — Integrate with `scripts/check` and pre-push

Append type checking to `scripts/check` so the canonical verification tool (per `AGENTS.md`) covers type errors during local development and on push. The existing `run-scripts-check` pre-push hook already runs `scripts/check`, so no new hook is needed:

```bash
echo "==> Static type check"
scripts/typecheck
```

`README.md` already documents `pre-commit install --hook-type pre-push` (line 433) — no change needed there.

### Phase 3 — CI integration

Add a `typecheck` job in `.github/workflows/ci.yml` that runs in parallel with `check`. Only Python 3.11 is needed — basedpyright checks at the configured `pythonVersion` floor, not per-version. The `gui` extra is required because `src/github_usage/gui/` contains top-level `from textual import ...` statements; without `textual` installed, `reportMissingImports = "error"` will fail the job:

```yaml
typecheck:
  runs-on: ubuntu-latest
  steps:
    - uses: actions/checkout@v7
    - uses: actions/setup-python@v6
      with:
        python-version: "3.11"
        cache: pip
    - name: Install package
      run: scripts/python -m pip install -e '.[dev,gui]'
    - name: Run basedpyright
      run: scripts/typecheck
```

The `[export-xlsx]` and `[export-pdf]` extras are not included: `openpyxl` and `fpdf2` are imported lazily (inside functions), so they will not produce missing-import errors during static analysis. Add them here only if Phase 1 reveals otherwise.

Python 3.11 is sufficient: basedpyright reports errors valid for the configured `pythonVersion`, which is the project minimum. Errors that would appear only on 3.12/3.13 are backward-incompatible patterns that are also errors on 3.11.

### Phase 4 — Follow-up hardening (future, out of scope)

Once the codebase is clean at `"standard"`, consider:
- Tightening `typeCheckingMode` to `"strict"`.
- Adding `reportUnknownMemberType`, `reportUnknownParameterType`, `reportUnknownVariableType` one at a time.
- Adding `--verifytypes github_usage` to the CI pipeline: this flag checks that the package's public API has complete type annotations, reporting any missing annotations on exported symbols. A CI failure would list each untyped public symbol.

## Verification

- `scripts/typecheck` exits 0.
- `scripts/check` includes `scripts/typecheck` and passes.
- `pre-commit run run-scripts-check --all-files --hook-stage pre-push` passes (exercises `scripts/check` → `scripts/typecheck`).
- `pre-commit run --all-files` passes (all non-pre-push hooks).
- `.github/workflows/ci.yml` typecheck job passes on a PR branch.

## CHANGELOG.md

Add under `[Unreleased] → ### Added`:

> - **basedpyright static type checking** ([plan](docs/superpowers/plans/2026-07-04-basedpyright-type-checking.md)): `basedpyright` runs on `src/` and `tests/` via `scripts/typecheck`, included in `scripts/check`, a pre-push hook, and a `typecheck` CI job. Existing codebase errors resolved or suppressed to establish a clean baseline. Devs run `pre-commit install --hook-type pre-push` to activate. Configurable via `[tool.basedpyright]` in `pyproject.toml`.
