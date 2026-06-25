# Repo Hygiene Plan

> **Status:** COMPLETED 2026-06-19 — archived from `docs/plan-repo-hygiene.md`
>
> These items are tracked in [TO_DO.md](../../../TO_DO.md#repo-engineering--hygiene). Each item below links back to its TO_DO.md entry.

## 1. Enforce file size limits

**TO_DO.md:** [Enforce file size limits](../TO_DO.md#L42)

### Current state

All source files are currently under 400 lines — no files violate the revised thresholds.

| File | Lines | Status |
|---|---|---|
| `src/github_usage/setup_wizard.py` | 389 | watch (approaching 400) |
| `src/github_usage/cli.py` | 374 | watch |
| `src/github_usage/report_summary.py` | 308 | ok |
| `src/github_usage/report_products.py` | 295 | ok |
| `src/github_usage/report_data.py` | 285 | ok |

No pre-commit hook or lint rule enforces file or function length.

### Revised thresholds (updated 2026-06-19)

The original 300-line / 50-line limits were too aggressive. The revised thresholds are:

- **500 lines per file** (warn at 400)
- **100 lines per function** (warn at 80)

These are soft warnings, not hard failures. Aggressive hard limits tend to accumulate skip-list exceptions or encourage over-fragmentation.

### Proposed approach

**Approach — custom script with warnings only**

Write `scripts/check-sizes` as a Python AST-based script that warns when files or functions approach the thresholds, but does not fail the build (exit 0 always). Add it to `scripts/check` output for visibility.

**Recommended implementation:**

1. Write `scripts/check-sizes` — a Python script that:
   - Iterates over `src/github_usage/**/*.py`
   - Warns (does not fail) if a file exceeds 400 lines; notes the 500-line hard concern
   - Uses AST to count function body lines; warns if any function exceeds 80 lines
   - Returns exit code 0 always (informational output only)

2. Add invocation to `scripts/check` so warnings appear during normal verification.

3. Optionally add as a non-blocking pre-commit hook:
   ```yaml
   - repo: local
     hooks:
       - id: check-sizes
         name: check file/function sizes (advisory)
         entry: python scripts/check-sizes
         language: system
         files: \.py$
         verbose: true
   ```
   Note: use `language: system` (not `language: script`) so pre-commit invokes the script via `python` rather than requiring it to be executable on PATH.

---

## 2. Agent guidance: keep files under 800 lines — DONE 2026-06-19

**Done:** Revised thresholds to 500-line file / 100-line function (soft guidance). Added "start extracting when approaching 400 lines" proactive signal to `AGENTS.md` Code Style. The original 800-line and 300-line thresholds were both revised (see plan notes above for rationale).

**TO_DO.md:** [Instruct agents via AGENTS.md](../TO_DO.md#L43)

### Current state

`AGENTS.md` Code Style section currently says:

> Keep files and functions small. If a file exceeds ~300 lines or a function exceeds ~50 lines, split it.

This is reactive — it tells agents to act *after* a threshold is breached. There is no proactive guidance.

### Proposed change

Add to `AGENTS.md` under **Code Style**:

```markdown
- Start extracting submodules or helpers when a file approaches 200 lines —
  do not wait for the 300-line threshold to trigger.
```

Note: the original draft proposed an 800-line "proactive" threshold, but that is counterproductive — an agent following it would allow files to grow to 799 lines before acting, which is nearly 3× the hard limit. The 200-line signal is the right prompt for proactive splitting.

### Implementation steps

1. Edit `AGENTS.md` to add the 800-line guidance line.
2. No code changes required.
3. Verify with `scripts/check` that the repo still passes.

---

## 3. Improve overall repo hygiene — DONE 2026-06-19

**Done:** Added `pyproject.toml` note to `AGENTS.md` Repository Expectations. No `.gitignore` or artifact changes needed (all were already correct per the assessment below).

**TO_DO.md:** [Improve overall repo hygiene](../TO_DO.md#L44)

### Current state

**`.gitignore`** — Already comprehensive:
- Covers `__pycache__/`, `*.pyc`, `.pytest_cache/`, `.ruff_cache/`, `.mypy_cache/`
- Covers `.env` files (with example preservation)
- Covers `build/`, `dist/`, `*.egg-info/`
- Covers `.venv/`, `venv/`, `env/`
- Covers `reports/`, `output/`, `*.log`, `*.sarif`, `junit/`
- Covers `.DS_Store`, `.idea/`, `.vscode/`, `tmp/`

**Assessment:** No action needed. `.gitignore` is complete.

**`pyproject.toml` / `requirements.txt`** — No `requirements.txt` exists.

**Assessment:** This is acceptable. The project uses `pyproject.toml` with setuptools, which is the modern standard. Extras are defined there (`dev`, `export-xlsx`, `export-pdf`, `test-xlsx`, `test-pdf`). No `requirements.txt` is needed unless there's a specific tool or CI that requires one.

**Recommendation:** No change. If a `requirements.txt` is desired for tools that need it, generate it from `pyproject.toml` using `pip-tools` or `uv export`, but this is optional.

**Stale artifacts** — Checked for tracked stale files:
- No `.pyc` files tracked in git (good)
- No `__pycache__/` directories tracked in git (good)
- No `.env` files tracked (only `.env.email-report.example` which is intentional)
- `tmp/` is gitignored (good)

**Assessment:** No stale artifacts are tracked.

### Implementation steps

1. No code changes needed for `.gitignore` or artifact cleanup.
2. Add a note to `AGENTS.md` under **Repository Expectations**:
   ```markdown
   - The project uses `pyproject.toml` for all dependency declarations.
     Do not create a `requirements.txt` unless a specific tool requires it.
   ```
3. Run `git ls-files --deleted` to confirm no files were accidentally deleted.

---

## 4. Add doc hygiene check

**TO_DO.md:** [Add a doc hygiene check](../TO_DO.md#L45)

### Current state

No automated check for:
- Public module/docstring coverage
- Consistency between `AGENTS.md`, `README.md`, and CLI `--help` text

### Proposed approach

**Docstring coverage check** (`scripts/check-docs` or `scripts/check-docstrings`):

1. Use `pydocstyle` or a custom script to check that all public modules and functions in `src/github_usage/` have docstrings.
2. Use ruff's `D` (pydocstyle) rules:
   - `D100` — module docstring
   - `D101` — public class docstring
   - `D102` — public method docstring
   - `D103` — public function docstring
   - `D104` — public package docstring

3. Add to `pyproject.toml`:
   ```toml
   [tool.ruff.lint.pydocstyle]
   convention = "google"
   ```

4. Add `D` rules to the *existing* `ruff` hook's `select` list in `pyproject.toml` — do NOT add a second `ruff-pre-commit` hook entry. Two separate ruff hooks with different `--select` args and `--fix` will conflict and produce unpredictable results.

**CLI help / docs consistency:**

This is harder to automate. A manual checklist approach is more practical:

1. Add a script `scripts/check-docs` that:
   - Runs `cli --help` and checks that all documented flags appear in `README.md`
   - Checks that `AGENTS.md` references match actual script paths
   - Reports discrepancies for manual review

2. Or: add a CI check that runs `scripts/docs-check` (which already exists) and ensures it passes.

### Implementation steps

1. Add ruff `D` rules to `pyproject.toml` with `pydocstyle` convention.
2. Run `ruff check --select=D src/github_usage/` to see current gaps.
3. Add docstrings to uncovered public functions (or selectively ignore with `# noqa: D10X` where appropriate, e.g., `__all__`-excluded internals).
4. Add `scripts/check-docs` script for CLI/README/AGENTS consistency (lightweight grep-based check).
5. Add docstring check to `scripts/check`.

---

## Cross-cutting considerations

### Ordering

These items are largely independent. Recommended execution order:

1. **Item 2** (AGENTS.md update) — single file edit, no risk
2. **Item 3** (repo hygiene) — mostly verification, minimal changes
3. **Item 4** (doc hygiene) — adds tooling, may require docstring additions
4. **Item 1** (file size enforcement) — adds tooling + requires refactoring 3 existing files

### Shared tooling

Items 1 and 4 both benefit from extending `scripts/check` and `.pre-commit-config.yaml`. Consider combining them into a single `scripts/check-hygiene` or adding both checks to the existing `scripts/check`.

### Risks

- **Item 1** (file size enforcement) may require significant refactoring of `cli.py`, `setup_wizard.py`, and `report_summary.py`. These should be done as separate PRs from the enforcement tooling.
- **Item 4** (docstrings) may reveal many uncovered functions. Start with a `--select=D` pass to assess scope before committing to full coverage.
