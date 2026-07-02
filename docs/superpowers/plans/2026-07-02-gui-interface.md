> **Status:** PROPOSED

**Date:** 2026-07-02

## Objective

Deliver a smooth, polished, cross-platform **Textual TUI** (terminal user interface) as the **default** way to use github-usage in an interactive terminal. **Command-line mode requires an explicit `--cli` flag.** This is **not** a native desktop GUI — it runs inside the terminal (including SSH sessions) using Textual.

The TUI replaces sequential CLI prompts with form-based inputs, real-time log streaming, interactive data tables, preview viewers, and asynchronous background worker execution. The existing bash menu (`./start.sh` choices), subcommands, and legacy token flow remain available via `--cli`.

To preserve the lightweight nature of the base CLI tool, Textual and all UI code are isolated in an optional dependency group (`[project.optional-dependencies]` → `gui` in `pyproject.toml`). Core CLI-only installs do not download Textual unless they install the extra (or run in TTY without it — see fallbacks below).

## Entry-point routing

**Default = TUI.** **CLI mode = `--cli`.** No separate `tui` subcommand.

| Invocation | TTY? | `[gui]` installed? | Behavior |
| :--- | :---: | :---: | :--- |
| `./start.sh` | yes | yes | Launch Textual TUI |
| `./start.sh` | yes | no | Print install hint; suggest `pip install 'github-usage[gui]'` or `./start.sh --cli` |
| `./start.sh` | no | — | Print usage help (CI-safe; same as today) |
| `./start.sh --cli` | yes | — | Current bash `show_menu()` (7 options) |
| `./start.sh --cli setup` | — | — | `./scripts/setup.sh` (unchanged) |
| `./start.sh setup` (etc.) | — | — | **Shortcut:** named commands still route directly to CLI without `--cli` (scripting / README compatibility) |
| `github-usage` | yes | yes | Launch Textual TUI |
| `github-usage` | yes | no | Install hint + suggest `--cli` |
| `github-usage` | no | — | Print `HELP` banner (CI-safe) |
| `github-usage --cli` | — | — | Print `HELP` banner |
| `github-usage --cli setup` | — | — | Setup wizard |
| `github-usage --cli [TOKEN] …` | — | — | Legacy usage report |
| `github-usage setup` (etc.) | — | — | **Shortcut:** named subcommands route to CLI without `--cli` |

**Routing rules (implementation):**

1. If argv contains `--cli`, strip it and continue with existing CLI dispatch (`setup`, `email-report`, `runs`, legacy token, help).
2. Else if the first arg is a **known subcommand** (`setup`, `email-report`, `runs`) or a **legacy token** (`ghp_…`, etc.), use CLI dispatch (shortcut — no `--cli` required).
3. Else if **interactive TTY** (`stdin.isatty()` and `stdout.isatty()`): launch TUI via `cli_gui.run_tui()`.
4. Else: print help (non-interactive default).

**`FORCE_INTERACTIVE=1`:** Applies only to `./start.sh --cli` bash menu smoke tests, not to TUI launch.

**Environment override (optional):** `GITHUB_USAGE_CLI=1` equivalent to passing `--cli` (for scripts that cannot easily insert the flag).

## Scope

### In scope (MVP — Phases 1–4)

| Area | Deliverable |
| :--- | :--- |
| Entry points | **Default:** `./start.sh` and `github-usage` launch TUI in a TTY. **CLI:** `--cli` flag or named subcommand shortcuts (`setup`, `email-report`, `runs`, `./start.sh setup`, …) |
| Setup | Secrets (`.env.email-report`), report options, multi-profile add/edit/delete, verify (`--dry-run`), status summary |
| Schedules | Edit local schedule + GitHub Actions cron in forms; regenerate launchd plist (macOS) and workflow YAML |
| Reports | Legacy usage report table + export; email report dry-run preview + send |
| Runs | Read-only scheduled-runs dashboard; drift check with full git orchestration |
| CI / tests | Lazy imports; headless Textual pilot tests; CI installs `[gui]` |

### Deferred to Phase 5 (wizard parity extensions)

These setup-wizard flows stay CLI-only until Phase 5. The TUI will link to them with “Run in terminal” guidance where applicable:

| Wizard option | Phase 5 action |
| :--- | :--- |
| GitHub Actions secrets (`gh secret set`) | TUI form that shells out to the same helpers as `setup_ci._configure_ci_secrets()` |
| Developer security hooks | Button invoking `setup_ci._configure_dev_hooks()` with streamed output |
| Git commit after workflow render | Modal offering “Write file only” vs “Write + open terminal for git commit” (wizard’s `_render_and_offer_commit()` is interactive git) |

Phase 5 is optional for the initial merge; Phases 1–4 satisfy the `TO_DO.md` item as a usable TUI alternative for day-to-day report and setup work.

## Current State & Challenges

- **Sequential CLI Prompts:** The current `start.sh` menu and `setup_wizard.py` guided setup rely on sequential terminal prompts (`input()`). Navigating back and forth between report profiles, email recipients, and schedule options is cumbersome.
- **Static Output Rendering:** Legacy usage reports and email reports output static tables or markdown to stdout. Reviewing results before sending requires generating an export file and manually inspecting it.
- **Blocking Execution:** Running usage queries or checking workflow drift (`runs-diff`) blocks terminal interaction until network calls complete.
- **Lack of Visual Drift & Schedule Dashboard:** Comparing local launchd schedules against GitHub Actions cron schedules requires separate commands (`runs` and `runs-diff`) and parsing text output.

## Setup Wizard Parity Map

The setup wizard (`setup_wizard.py`) exposes these actions. The TUI maps each to a screen or defers explicitly:

| Wizard key | Label | TUI screen / action | Phase |
| :--- | :--- | :--- | :--- |
| 1 | Recommended full setup | Onboarding checklist linking Setup + Schedules sub-flows | 1 |
| 2 | Local email secrets only | Setup → Secrets panel | 1 |
| 3 | Report options only | Setup → Report options panel | 1 |
| 4 | Report schedule only | Schedules → Local schedule form | 3 |
| 5 | GitHub Actions workflow | Schedules → GitHub Actions form + “Regenerate workflow file” | 3 |
| 6 | macOS launchd schedule | Schedules → LaunchAgent install/remove (macOS only) | 3 |
| 7 | GitHub Actions secrets | Deferred — link to `./start.sh setup` option 7 | 5 |
| 8 | Developer security hooks | Deferred — link to `./start.sh setup` option 8 | 5 |
| 9 | Verify configuration | Setup → Verify button | 1 |
| m | Manage report profiles | Setup → Profile selector (+ Add / Edit / Delete) | 1 |
| 0 | Show status | Setup → Status sidebar (masked env summary + LaunchAgent state) | 1 |

## TUI Framework Evaluation & Selection

| Framework Option | Pros | Cons | Verdict |
| :--- | :--- | :--- | :--- |
| **Option A: Textual (Modern Python TUI)** | Lightweight, SSH-compatible, mouse support, modals, tabs, `DataTable`, TCSS styling, headless `app.run_test()` for CI. Works on macOS, Windows, Linux, SSH, Docker. | Renders in terminal cells, not a native OS window. No native file-save dialog. | **RECOMMENDED.** |
| **Option B: PySide6 (Qt 6)** | Native desktop windowing, file dialogs, embedded preview. | ~100MB+ wheels; fails headless/SSH without display server hacks. | Alternative only if desktop-native is required. |
| **Option C: Flet / NiceGUI** | Web-style layouts. | Webview complexity; weaker CLI integration. | **Not recommended.** |

### Architecture Decision: Textual with Backend Service Layer

We select **Textual** as the interface framework. Core requirements:

1. **Lazy Import Mandate:** `textual` and TUI views **must never be imported at module level** in `cli.py` or `cli_parsers.py`. They load lazily in `src/github_usage/cli_gui.py`, invoked only on the default TTY path (step 3 in Entry-point routing). `github-usage --help` and `github-usage --cli --help` are handled without importing Textual (exit `0`).

2. **Backend Service Layer (`src/github_usage/gui_backend.py`):** Views must **not** import private `_`-prefixed functions from setup or CLI modules. Add a thin public module that wraps existing logic:

   | Public function | Wraps / uses |
   | :--- | :--- |
   | `load_setup_paths()` | `SetupPaths.from_root()` |
   | `read_secrets()` / `write_secrets()` | `read_env_file()` / `write_env_file()` |
   | `load_profiles()` / `save_profiles()` | `load_config()` / `ensure_profiles()` / `write_config()` |
   | `verify_configuration(paths, profile?)` | Same dry-run loop as `setup_wizard._verify_setup()` with stdout/stderr capture |
   | `run_legacy_report(...)` | `GitHubAPI` + `legacy_report` / `export_report` |
   | `run_email_dry_run(...)` / `send_email_report(...)` | `cli.main(['email-report', ...])` or public email-report helpers |
   | `list_scheduled_runs(paths, profile?)` | `list_local_runs()` |
   | `check_workflow_drift(paths, profile?, skip_fetch?)` | Full orchestration from `cli_runs._run_diff()`: `check_prerequisites`, `fetch_remote`, `resolve_remote_name`, `resolve_default_branch`, `classify_drift`, `render_drift` — returns structured rows, not scraped stdout |
   | `regenerate_launchd_plist(paths, profile)` | `generate_plist()` |
   | `install_launch_agent(paths)` / `launch_agent_status(paths)` | Existing `setup_launchd` public functions |
   | `regenerate_workflow_file(paths, profile)` | Non-interactive path through `setup_workflow` render (write YAML; git commit deferred to Phase 5) |
   | `configure_schedule_fields(...)` | Writes schedule fields to config via `write_config()` (no `input()` loops) |
   | `status_summary(paths)` | `status_lines()` + `launch_agent_status()` + `is_minimally_configured()` |

   New code in `gui_backend.py` only; no additions to `setup_config.py` (507 lines, over limit) or `setup_wizard.py` (461 lines).

3. **Strict Decoupling (MVC):** `src/github_usage/gui/` is presentation + controllers only. Controllers call `gui_backend.py`; they do not call `setup_wizard`, `cli_runs`, or private setup helpers directly.

4. **Asynchronous Workers & Clean Shutdown:** Network, Git, and email work runs on background workers (`@work(thread=True)` or `app.run_worker()`), posting messages to the main loop. `on_unmount` cancels or awaits active workers. Verification and subprocess output use `contextlib.redirect_stdout`/`redirect_stderr` to a thread-safe buffer that posts to a `RichLog` widget — never writing raw stdout into the Textual screen.

5. **Platform-Aware Scheduling:** `sys.platform == "darwin"` gates launchd install/remove controls. On Windows/Linux, show an informational badge: *“Local launchd scheduling is macOS-only. Use the GitHub Actions panel for cross-platform cloud schedules.”*

6. **Security & Secrets:** Masked `Input(password=True)` widgets. Persist secrets only via `write_secrets()` → `write_env_file()` (mode `600`). Do not log secrets or billing report bodies. Widget memory may hold edited values until Save or quit — document that this is expected; do not claim “never in memory.”

7. **Line Limits:** `cli.py` is 402 lines (soft warning at 400). Extract TUI dispatch to `cli_gui.py`. All new TUI code lives in `src/github_usage/gui/`, `gui_backend.py`, and `cli_gui.py`.

### Naming

- **No `tui` subcommand.** TUI is the default; document as “run `./start.sh` or `github-usage`”.
- **CLI mode:** global `--cli` flag on `github-usage` and `./start.sh`.
- **pip extra:** keep `[gui]` (`pip install 'github-usage[gui]'`) — dependency group name, not a subcommand.

## Target Features & UI/UX Design

### 1. Main Application Layout & Navigation

Bare `./start.sh` or `github-usage` in a TTY opens the Textual app directly (no bash menu). Sidebar navigation:

```text
+-----------------------------------------------------------------------------+
|  github-usage (Textual)                                    [Theme: Dark] [q] |
+---------------------+-------------------------------------------------------+
|  NAVIGATION         |  Setup & Report Profiles                              |
|                     |                                                       |
|  > Setup & Profiles |  Active Profile: [ default v ]  (+ Add) (Edit) (Del)  |
|    Usage Report     |                                                       |
|    Email Report     |  +-- Secrets & Auth (.env.email-report) -----------+  |
|    Schedules        |  | GitHub Token: [ ************************ ] (Show)|  |
|    Runs & Drift     |  | Resend API Key: [ ********************** ] (Show)|  |
|                     |  | Report Email:   [ user@example.com         ]       |  |
|                     |  +-------------------------------------------------+  |
|                     |                                                       |
|                     |  +-- Report Options (config.toml) -----------------+  |
|                     |  | [x] Include Top Consumers   Max Repos: [ 50  ]  |  |
|                     |  | [x] Include Storage         Warn Over: [ $100]  |  |
|                     |  | [ ] Include Release Assets                      |  |
|                     |  +-------------------------------------------------+  |
|                     |                                                       |
|                     |  [ Verify Configuration ]   [ Save Profile ]          |
|                     |                                                       |
|                     |  +-- Verification Log (Live Stream) ---------------+  |
|                     |  | > Ready to verify configuration...              |  |
|                     |  +-------------------------------------------------+  |
+---------------------+-------------------------------------------------------+
```

### 2. Core Feature Screens

- **Setup & Profiles (`views/setup_view.py`, `controllers/setup_controller.py`):**
  - Multi-profile management via `gui_backend.load_profiles()` / `save_profiles()` (`[[reports]]` in `config.toml`).
  - Form fields for secrets; Save calls `write_secrets()` only (no `_configure_env_secrets()` prompts).
  - Status sidebar from `status_summary()`.
  - Verify button → `verify_configuration()` on a worker with streamed log output.

- **Schedules (`views/schedules_view.py`):**
  - Local schedule (weekday/hour/minute) and GitHub Actions cron (UTC) forms per profile.
  - “Regenerate plist” / “Install LaunchAgent” / “Remove LaunchAgent” on macOS via `gui_backend` launchd helpers.
  - “Regenerate workflow YAML” writes `.github/workflows/email-report*.yml` without interactive git commit (Phase 5 adds commit UX).

- **Legacy Usage Report (`views/report_view.py`):**
  - Parameter bar: token override, timeout, max retries, export format (csv, xlsx, pdf, json, text).
  - Summary cards and sortable `DataTable` for top consumers.
  - **Export UX:** Path `Input` + Browse hint (paste absolute path; Textual has no native OS save dialog). If xlsx/pdf selected and optional extra missing, show install hint (`pip install github-usage[export-xlsx]`).

- **Email Report & Preview (`views/email_report_view.py`):**
  - Profile selector (`--profile`), section toggles, recipient/subject overrides.
  - Dry-run preview tab (`Markdown` or `RichLog`); Send behind confirmation modal on a worker.

- **Runs & Drift (`views/runs_view.py`):**
  - Table from `list_scheduled_runs()` with human-readable schedules (reuse `describe_cron_human` / profile labels from `cli_runs`).
  - “Check drift” → `check_workflow_drift()` (full git orchestration, not `classify_drift()` alone).
  - Color-coded drift badges from structured `drift` field.

### 3. UX Polish & Error Handling

- Spinners/status bars during API and Git operations.
- `ModalScreen` for rate limits, network errors, missing `[gui]` / export extras — actionable text, no tracebacks in the UI.
- Keyboard: Tab navigation, `ctrl+s` save, `q` / `ctrl+c` quit.

## Dependency & Packaging Plan

1. **`pyproject.toml`:**
   ```toml
   [project.optional-dependencies]
   gui = [
       "textual>=0.70.0",
   ]
   ```
   Keep the extra name `gui` (pip convention); there is no `tui` subcommand.

2. **CLI integration (`cli.py`, `cli_parsers.py`, `cli_gui.py`):**
   - Add global `--cli` flag to top-level parsing (before subcommand dispatch).
   - Default TTY path in `cli.main()` → `cli_gui.run_tui()` when no `--cli`, no subcommand, and no legacy token.
   - Update `cli.py` `HELP` to lead with TUI default and document `--cli` for command-line mode.
   - `cli_gui.py`: lazy-import Textual; on `ImportError`, print:
     ```text
     Error: TUI dependencies are not installed.
     To launch the terminal interface, install the optional gui package:
       pip install 'github-usage[gui]'
     Or if developing locally:
       uv pip install -e '.[gui]'
     Or use command-line mode:
       github-usage --cli
       ./start.sh --cli
     ```
     Exit code `1`.

3. **`start.sh`:**
   - **Default (no args):** if TTY → `exec … -m github_usage` (Python routes to TUI); if non-TTY → `show_help` (unchanged CI behavior).
   - **`--cli` with no subcommand:** if TTY → `show_menu()` (existing 7-option bash menu); if non-TTY → `show_help`.
   - **`--cli` parsing:** accept `--cli` before any subcommand; strip and forward remainder.
   - **Named subcommands** (`setup`, `report`, …): unchanged shortcuts — no `--cli` required.
   - Add `--cli` to `show_help()` global options.
   - Keep `scripts/smoke` bash-menu test as `FORCE_INTERACTIVE=1 ./start.sh --cli` with choice `7` (Exit) — menu is CLI-only now.

## CI & Test Strategy

- **GitHub Actions (`.github/workflows/ci.yml`):** Change install step to `python -m pip install -e '.[gui]'` so Textual is available for pilot tests.
- **GUI tests:** `tests/test_gui_*.py` use `app.run_test()`. Each module starts with:
  ```python
  import unittest
  textual = __import__("unittest").importModule("textual")  # or skipUnless find_spec
  ```
  Prefer requiring `[gui]` in CI rather than skipping — keeps coverage honest.
- **`scripts/check`:**
  - Non-TTY: `./start.sh </dev/null` still prints usage (unchanged).
  - Non-TTY: `github-usage` still prints help / fails token check as today — use `github-usage --cli` in smoke where legacy no-token behavior is tested.
  - TTY smoke (optional): verify `github-usage --cli --help` exits `0` without importing Textual.
- **`scripts/smoke`:**
  - Bash menu: `FORCE_INTERACTIVE=1 ./start.sh --cli` with choice `7` (Exit).
  - Assert bare `github-usage --cli` with no `[gui]` does not require Textual.
  - CI no-token test: `github-usage --cli` (not bare `github-usage`, which would launch TUI when TTY).
- **`scripts/docs-check`:** README documents TUI-as-default and `--cli` for CLI/bash menu.

## Proposed Implementation Plan

### Phase 1: Foundation, entry-point routing, Setup screen

- [ ] Add `gui_backend.py` with public wrappers listed above (implement verify, secrets, profiles, status first).
- [ ] Add `cli_gui.py` with lazy Textual import and missing-deps message.
- [ ] Implement `--cli` flag and default-TTY → TUI routing in `cli.py`; update `HELP`.
- [ ] Update `./start.sh`: bare TTY → Python (TUI); `--cli` → bash menu; non-TTY → help; preserve named-command shortcuts.
- [ ] Create `src/github_usage/gui/` layout: `app.py`, `main_window.py`, `workers.py`, `styles/app.tcss`.
- [ ] Implement Setup & Profiles view (secrets, options, profile CRUD, verify, status sidebar).
- [ ] Add `tests/test_gui_models.py` (pilot tests for setup form save/verify).
- [ ] Add `pyproject.toml` `[gui]` extra.
- [ ] Update `scripts/check` / `scripts/smoke` for new routing (see CI & Test Strategy).

### Phase 2: Reporting & Preview

- [ ] Implement Usage Report view (API worker, `DataTable`, export path input, optional-extra hints).
- [ ] Implement Email Report view (profile selector, dry-run preview, send modal).
- [ ] Add `tests/test_gui_reports.py`.

### Phase 3: Schedules & Runs

- [ ] Implement Schedules view (local + GitHub cron forms, plist/workflow regeneration, macOS launchd controls).
- [ ] Implement Runs & Drift view (`list_scheduled_runs`, `check_workflow_drift` with full git flow).
- [ ] Add `tests/test_gui_runs.py`.

### Phase 4: Documentation & Verification

- [ ] Update `README.md` (TUI as default; `--cli` for bash menu and explicit CLI mode; subcommand shortcuts unchanged).
- [ ] `CHANGELOG.md` entry under `[Unreleased] → Added`.
- [ ] Extend `scripts/check` and `scripts/smoke` per CI & Test Strategy above.
- [ ] Update `.github/workflows/ci.yml` to install `.[gui]`.
- [ ] Run `scripts/check`, `scripts/smoke`, `scripts/docs-check`.
- [ ] Remove `TO_DO.md` GUI item on merge.

### Phase 5 (optional follow-up): Wizard parity extensions

- [ ] CI secrets panel (`gh secret set` via `setup_ci` helpers, streamed output).
- [ ] Developer hooks install button.
- [ ] Workflow render + optional git commit modal.

## Definition of Done (Phases 1–4)

- [ ] New code in `src/github_usage/gui/`, `gui_backend.py`, and `cli_gui.py` only; files ≤400 lines, functions ≤100 lines. No new logic in `setup_config.py` or `setup_wizard.py`.
- [ ] `[gui]` extra in `pyproject.toml`; `textual` lazy-imported; `--cli`, subcommand shortcuts, and non-TTY invocations never require Textual.
- [ ] Views call `gui_backend.py` only — no direct imports of `_`-prefixed setup/CLI symbols.
- [ ] Background work uses Textual workers; clean shutdown on exit.
- [ ] CI installs `.[gui]`; `scripts/check`, `scripts/smoke`, `scripts/docs-check` pass.
- [ ] Secrets not logged; `.env.email-report` written at mode `600`.
- [ ] `CHANGELOG.md` updated; `TO_DO.md` item removed when shipped.
- [ ] Plan status set to `> **Status:** COMPLETE` and file moved to `docs/superpowers/plans/archived/` in the same change set as the implementation, before commit/merge.
