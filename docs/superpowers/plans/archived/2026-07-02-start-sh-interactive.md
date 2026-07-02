> **Status:** COMPLETE

**Date:** 2026-07-02

## Objective

Make [start.sh](start.sh) present users with an interactive options menu when executed without arguments in an interactive terminal session, rather than requiring command-line flags.

## Context & Background

Currently, [start.sh](start.sh) displays the standard help/usage banner and exits when called with no arguments or `--help`.

According to [docs/start-sh-interactive-research.md](docs/start-sh-interactive-research.md), the repository follows a strict zero-dependency requirement for testing and execution, and uses standard `unittest` and shell scripts like [scripts/smoke](scripts/smoke) for validation. CI (`.github/workflows/ci.yml`) runs `scripts/check` only — not `scripts/smoke` — so any regression guard for bare `./start.sh` must land in `scripts/check` (or be added there) to run in CI.

[README.md](README.md) already tells users to "Run `./start.sh` for guided configuration" and references numbered choices such as **GitHub Actions secrets** and **macOS launchd schedule**. Those names and numbers belong to the **setup wizard** (`./start.sh setup`), not the new top-level menu. One passage also mislabels launchd as wizard option **4**; the wizard assigns launchd to option **6** and report schedule to option **4**. Phase 3 rewrites affected README sections using a **two-step flow** (`./start.sh` → top-level **1** → wizard **N**) or the `./start.sh setup` shortcut.

To support non-interactive execution (e.g. automated smoke tests or CI tasks), the interactive options menu should only be displayed when standard input is a TTY (`[ -t 0 ]`), or when an explicit test override (`FORCE_INTERACTIVE=1`) is set. Otherwise, it must gracefully fall back to the standard non-interactive help banner.

`FORCE_INTERACTIVE` is a **shell-layer test hook only** for the `start.sh` menu. It does not bypass Python `sys.stdin.isatty()` checks in `setup_wizard.py` or `cli.py`. Selecting **setup** from the menu still requires a real TTY for the Python wizard unless the user passes `--status` / `--verify`. No Python changes are in scope for this plan.

## Review Notes (2026-07-02)

Gaps and corrections identified during plan review:

| Issue | Resolution |
|-------|------------|
| `FORCE_INTERACTIVE=0` would still trigger interactive mode with `[ -n "${FORCE_INTERACTIVE:-}" ]` | Check `FORCE_INTERACTIVE=1` explicitly |
| CI runs `scripts/check`, not `scripts/smoke` | Add non-interactive bare `./start.sh` assertion to `scripts/check` |
| README implies `./start.sh` is already interactive but conflates setup-wizard option numbers with a top-level menu; launchd cited as wizard option **4** but is option **6** | Phase 3 rewrites every affected README passage using the two-step flow convention |
| No invalid-input handling specified | Re-prompt on empty/unknown choices |
| `exec "$0"` breaks when invoked as `bash start.sh` from another directory | Re-exec via `"$ROOT_DIR/start.sh"` |
| `show_help()` / `show_menu()` placement unspecified | Define both functions before the top-level `case` |
| TO_DO cleanup not listed | Remove the matching `TO_DO.md` item when complete |
| Research doc's Python `FORCE_INTERACTIVE` bypass is out of scope | Documented above; no `setup_wizard.py` changes |

## Definition of Done

- Running `./start.sh` without arguments in an interactive terminal session (`[ -t 0 ]`) presents a menu with options to run each subcommand.
- Selecting a command from the menu runs the corresponding functionality (e.g. `setup`, `report`, `email-report`, `runs`, `runs-diff`).
- Running `./start.sh` in a non-interactive context (e.g. redirected stdin, CI runner, piping) without arguments displays the standard help banner and exits with status 0.
- Standard command invocation (e.g. `./start.sh setup`) and flag help invocation (`./start.sh --help`) continue to function exactly as before without presenting any additional top-level menu.
- `scripts/check` includes a non-interactive bare `./start.sh` assertion so CI cannot regress into a hang or unexpected prompt.
- A smoke test is added to [scripts/smoke](scripts/smoke) that uses `FORCE_INTERACTIVE=1` with redirected input (heredoc) to verify the menu outputs expected options and exits successfully.
- `./scripts/check` and `./scripts/docs-check` pass.
- [CHANGELOG.md](CHANGELOG.md) is updated under `[Unreleased]` -> `### Added` with a summary of the new interactive options menu.
- [README.md](README.md) documents both menu layers, uses the two-step flow convention for every wizard-specific instruction, and fixes incorrect wizard option numbers (notably launchd = **6**, not **4**).
- The matching item is removed from [TO_DO.md](TO_DO.md) when the plan is complete.

## Proposed Implementation Plan

### Phase 1: Implement Interactive Menu in `start.sh`

- [x] **Done:** 2026-07-02 — Backed up [start.sh](start.sh) to `backups/start.sh.bak`.
- [x] **Done:** 2026-07-02 — Refactored help block into `show_help()`; placed `show_help()` and `show_menu()` above the `case` dispatcher.
- [x] **Done:** 2026-07-02 — Separated `-h|--help)` from empty command handler; `--help` never launches the menu.
- [x] **Done:** 2026-07-02 — Implemented `show_menu()` with numbered options 1–7, invalid-input re-prompt, `read -r choice || exit 0`, and `exec "$ROOT_DIR/start.sh" <command>` for subcommands.
- [x] **Done:** 2026-07-02 — Empty command handler uses `[ -t 0 ]` or `FORCE_INTERACTIVE=1` for menu; otherwise `show_help` + exit 0.

### Phase 2: Add Test Integration

- [x] **Done:** 2026-07-02 — Added non-interactive bare `./start.sh` guard to [scripts/check](scripts/check).
- [x] **Done:** 2026-07-02 — Added `FORCE_INTERACTIVE=1` menu smoke test to [scripts/smoke](scripts/smoke).
- [x] **Done:** 2026-07-02 — Added non-interactive fallback smoke test to [scripts/smoke](scripts/smoke).

### Phase 3: Documentation, Verification & Changelog

#### Two menu layers (document in README)

After implementation, users encounter **two** numbered menus. README must never mix their option numbers.

| Layer | Invocation | Options (summary) |
|-------|------------|-------------------|
| **Top-level** `start.sh` menu | `./start.sh` (TTY) | **1** setup · **2** report · **3** email-report · **4** runs · **5** runs-diff · **6** help · **7** exit |
| **Setup wizard** menu | `./start.sh setup` or top-level **1** | **1** full setup · **2** secrets · **3** report options · **4** report schedule · **5** GitHub Actions workflow · **6** macOS launchd · **7** GitHub Actions secrets · **8** dev hooks · **9** verify |

Source of truth for wizard labels/numbers: `_MENU_OPTIONS` in [setup_wizard.py](src/github_usage/setup_wizard.py).

#### README documentation convention

Use this pattern wherever README refers to a **setup-wizard** choice:

> Run `./start.sh`, choose **1** (Run Guided Setup), then choose **N** (*wizard label*) — or run `./start.sh setup` and choose **N**.

For **top-level** commands, either form is fine:

> Run `./start.sh` and choose **4** (View Scheduled Runs) — or run `./start.sh runs`.

Add a short **“Interactive menus”** subsection under **Setup** that shows both menus (or a compact table) and states the convention once so later sections can use the shorthand “setup wizard option **N**” after first introducing the two-step flow.

**Example rewrite** (GitHub Actions secrets):

> Run `./start.sh`, choose **1** (Run Guided Setup), then choose **7** (GitHub Actions secrets) — or run `./start.sh setup` and choose **7** — to set repository secrets with `gh secret set`:

#### README line-by-line fixes (required)

- [x] **Done:** 2026-07-02 — Added **Interactive menus** subsection under Setup.
- [x] **Done:** 2026-07-02 — Fixed Configuration → GitHub Actions workflow to use two-step flow / wizard option **5**.
- [x] **Done:** 2026-07-02 — Fixed launchd/schedule mix-up (wizard **4** / **5** / **6**).
- [x] **Done:** 2026-07-02 — Fixed GitHub Actions secrets reference to wizard option **7**.
- [x] **Done:** 2026-07-02 — Expanded Scheduled Email Reports entry point.
- [x] **Done:** 2026-07-02 — Fixed GitHub Actions Setup secrets instructions.
- [x] **Done:** 2026-07-02 — Fixed macOS launchd Setup section.
- [x] **Done:** 2026-07-02 — Fixed Development hooks section (wizard **8**).
- [x] **Done:** 2026-07-02 — Added top-level menu equivalents for runs / runs-diff.
- [x] **Done:** 2026-07-02 — Consistency pass completed.

#### Verification & changelog

- [x] **Done:** 2026-07-02 — `./scripts/check` passed.
- [x] **Done:** 2026-07-02 — `./scripts/smoke` passed.
- [x] **Done:** 2026-07-02 — `./scripts/docs-check` passed.
- [x] **Done:** 2026-07-02 — Added CHANGELOG entry under `[Unreleased]` → `### Added`.
- [x] **Done:** 2026-07-02 — Removed matching item from [TO_DO.md](TO_DO.md).

## Out of Scope

- Python `FORCE_INTERACTIVE` / `--test-input` bypasses for `setup_wizard.py` or `cli.py` `isatty()` gates (see research doc Option B; not required for the bash menu layer).
- PTY emulation, `expect`/`pexpect`, or new test dependencies.
- Changes to setup-wizard option numbering or behavior.
- A `start.ps1` Windows entrypoint (tracked separately in `TO_DO.md`).

## Edge Cases (accepted)

- **Stdout redirected, stdin TTY** (`./start.sh > log.txt`): menu still runs because `[ -t 0 ]` is true; user sees no prompt on screen. Same class of issue as many CLI tools; not addressed here.
- **Menu option 6 (help)**: exits after printing help rather than returning to the menu; user can re-run `./start.sh`.
