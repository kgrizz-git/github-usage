# [2026-07-02] Implementation Plan — Legacy Report Single Fetch (Fix #2, Option A)

> **Status:** COMPLETE

## Objective

Eliminate **duplicate GitHub API calls** on the legacy CLI path when `--export` is used (and on every interactive legacy run today). Adopt **Option A** from the [2026-06-21 bug report](../../assessments/bug-report-20260621-000000.md): **fetch once** via a structured report dict, then **render twice** — terminal display and file export — without re-querying billing endpoints.

Tracked in `TO_DO.md` as *Refactor to eliminate double API calls on legacy export*.

> **For agentic workers:** Steps use checkbox (`- [ ]`) syntax for tracking.

---

## Problem (Current State)

When a user runs `github-usage --export csv` (or picks an export format at the interactive prompt):

1. `legacy_main()` → `_run_report_body()` drives the terminal report. Every `show_*` function fetches billing data inline (`get_user_actions_billing`, `get_actions_per_repo`, `get_billing_summary`, `get_storage_analysis`, etc.).
2. `_run_legacy_report()` in `cli.py` then calls `report_data.build_report_data()` **again** to populate the export file.

The two pipelines overlap heavily. For accounts with many repositories, billing summary and per-repo calls run **twice**. Output is correct; quota consumption is not.

**Not affected today:** `email-report` (single `build_report_data`), TUI legacy screen (`gui_backend.run_legacy_report_data`), and legacy runs **without** export still make only one pass — but that pass uses the older `show_*` fetch-in-print path, not `build_report_data`.

**Hidden duplication risk (single-fetch must avoid):** Even after merging the two pipelines, naively calling both `get_artifact_storage_details` / `_fetch_sections` and `get_storage_analysis` would **double-fetch** `/actions/artifacts` and `/releases` per repo. Likewise, calling `get_repo_consumers` after `fetch_repo_actions_table` would **double-fetch** per-repo Actions billing. Phase 1 must derive derived sections from primary fetches (see below).

---

## Architecture Decision — Option A

```
┌─────────────┐     build_legacy_report_data()      ┌──────────────────┐
│  GitHubAPI  │ ──────────────────────────────────► │  report dict     │
└─────────────┘    (one fetch pass; derive slices)   │  (JSON-serializable)
                                                    └────────┬─────────┘
                                                             │
                              ┌──────────────────────────────┼──────────────────────────────┐
                              ▼                              ▼                              ▼
                    render_legacy_report()          export_report.export()          gui_backend (same dict)
                    (stdout, no API)                (csv/json/xlsx/pdf/text)
```

**Principles:**

1. **Fetch layer** — `legacy_report_data.build_legacy_report_data()` builds a **superset** dict for terminal + export. Primary fetches run once; derived keys (`repo_consumers`, `artifact_storage`, `release_assets`) are **computed from** `repo_actions` and `storage_analysis`, never re-fetched.
2. **Render layer** — new `render_*` functions print from dict slices only; **no `api` parameter**, no network I/O.
3. **Export layer** — unchanged `export_report.export(data, …)`; it already consumes the structured dict.
4. **Compatibility** — existing public `show_*` names stay in `legacy.py` as thin deprecated wrappers (fetch + render, or render-only) so external callers and `tests/test_legacy_compat.py` do not break.
5. **Module placement** — orchestrator lives in **`src/github_usage/legacy_report_data.py`** from the start (`report_data.py` is 352 lines; `AGENTS.md` extraction threshold is ~400).

**Non-goals (this plan):**

- Deduplicating *all* billing summary re-fetches within one pass (e.g. `get_monthly_costs` after `get_actions_usage`) — worthwhile follow-up, separate item.
- Changing `email-report` flow (stays on `build_report_data` unless later unified).
- Historical `--month` billing (blocked by API; see `docs/api-discovery-month.md`).

---

## Legacy Terminal ↔ Report Dict Parity Map

| Legacy section (`show_*`) | Fetches today | In `build_report_data` today? | Plan |
| :--- | :--- | :---: | :--- |
| `print_header` | — | — | Render only (static) |
| `show_account_info` | `GET /user` | No | Add `account` key |
| `show_rate_limits` | `GET /rate_limit` (full resources) | Partial (`_rate_limit` reads core only) | Add `rate_limits` key (full payload) |
| `show_actions_summary` | `get_user_actions_billing` | Yes (`actions`) | `render_actions_summary(data["actions"])` |
| `show_actions_per_repo` | per-repo billing × N repos | Partial (`repo_consumers` = top 5 only) | Add `repo_actions` (full table rows) — **primary fetch** |
| `show_actions_top_consumers` | derived | derived from `repo_consumers` | Render from `repo_actions` / `repo_consumers` |
| `show_actions_os_breakdown` | `get_actions_from_runs` × up to 10 repos | No | Add `actions_os_breakdown` key |
| `show_copilot_summary` | billing + premium | Yes (`copilot`) | `render_copilot_summary(data["copilot"])` |
| `show_gitlfs_summary` | billing | Yes (`git_lfs`) | `render_gitlfs_summary(data["git_lfs"])` |
| `show_monthly_costs` | billing (again) | Yes (`monthly_costs`) | `render_monthly_costs(…)` |
| `show_full_billing_history` | `get_full_billing` | No | Add `billing_history` key |
| `show_limits_summary` | derived | derived from `actions` | `render_limits_summary(data["actions"])` |
| `show_base_costs` | billing summaries | partial | Render from `actions` + `copilot` + `git_lfs` sku/items |
| `show_final_summary` | `get_storage_analysis`, premium | partial (`insights` only) | `storage_analysis` key; premium from `copilot.by_model` |
| `show_what_else` | — (static text) | — | `render_what_else(username)` — no fetch |

**Repo list:** fetch `/user/repos` **once** with `limit=max_repos` (100 for legacy default); share across all repo-scoped sections.

**Derived sections (no extra API calls):**

| Derived key | Source | Rule |
| :--- | :--- | :--- |
| `repo_consumers` | `repo_actions` | Sort/slice rows for `by_minutes` / `by_cost` (top 5); copy `errors` from per-repo fetch |
| `artifact_storage` | `storage_analysis` | Aggregate artifact bytes per repo from `storage_analysis["repos"]` items where `type == "Artifact"` |
| `release_assets` | `storage_analysis` | Aggregate release asset bytes from items where `type == "Release Asset"` (when `include_release_assets=True`) |

**Do not call** `get_repo_consumers`, `get_artifact_storage_details`, or `get_release_asset_details` inside `build_legacy_report_data`.

**Export flags for legacy default** (match current `_run_legacy_report`):

```python
include_actions=True,
include_copilot=True,
include_lfs=True,
include_consumers=True,          # satisfied via derived repo_consumers
include_artifact_storage=True,   # satisfied via derived artifact_storage
include_release_assets=False,
max_repos=100,
```

---

## Extended Report Dict Schema (Legacy Superset)

Add keys alongside the existing export schema (`tests/fixtures/export_report_data.json`). New fixture: `tests/fixtures/legacy_report_data.json` (superset of export fixture).

| Key | Type | Purpose |
| :--- | :--- | :--- |
| `account` | `{login, type, …}` | Header / account line |
| `rate_limits` | `{resources: {…}}` | Full rate-limit table |
| `repo_actions` | `[{repo, minutes, storage_gb_hours, avg_mb, gross, sku}]` | Full per-repo Actions table (primary) |
| `actions_os_breakdown` | `{repos: [{name, os_minutes}], totals}` | OS breakdown section |
| `billing_history` | `[usageItems…]` | Full billing history section |
| `storage_analysis` | `{repos: […]}` | Final summary + source for `artifact_storage` / `release_assets` |

Existing keys (`actions`, `copilot`, `git_lfs`, `monthly_costs`, `repo_consumers`, `artifact_storage`, `errors`, `warnings`, `insights`, `api_estimate`) stay stable so **export and email formatters do not break**.

Document the schema in the `legacy_report_data.py` module docstring.

---

## API Quota Estimation (Legacy Superset)

`estimate_api_request_count` today only counts optional flags (`include_consumers`, `include_artifact_storage`, etc.) and would **under-estimate** the legacy path if those flags imply separate fetches.

In `build_legacy_report_data`:

- Compute `api_estimate` from the **actual** legacy fetch plan, approximately:
  - `GET /user`, `GET /rate_limit`
  - Product billing summaries (actions, copilot, lfs, monthly_costs, billing_history)
  - Per repo (up to `max_repos`): one Actions billing summary (`repo_actions`) + artifacts + releases (`storage_analysis` — counted once, not twice)
  - Up to 10 repos: workflow runs for OS breakdown
- Attach accurate `api_estimate` to the returned dict (exported JSON and pre-fetch quota guard).
- Pre-fetch guard: reject when `core_remaining < estimated_incremental_requests` (same policy as `build_report_data` today).

Add unit tests for the legacy estimate formula (mock repo count, assert no double-count of artifact/release endpoints).

---

## Phase 1 — Fetch Orchestrator (`legacy_report_data.py`)

- [ ] Create **`src/github_usage/legacy_report_data.py`** (do not add orchestrator to `report_data.py`).
- [ ] Add fetch helpers in focused modules:
  - `report_account.py`: `fetch_account_info(api) -> dict`, `fetch_rate_limits(api) -> dict`
  - `report_actions.py`: `fetch_repo_actions_table(api, repos) -> tuple[list[dict], dict[str, str]]` — per-repo `BillingFetchError` recorded in errors dict (same resilience as `get_repo_consumers`); failed repos skipped, report continues
  - `report_actions.py`: `fetch_actions_os_breakdown(api, repos, *, limit=10) -> dict`
  - `report_products.py`: `fetch_billing_history(api, username) -> list`
  - Reuse `storage.get_storage_analysis(api, repos)` — **once**; store on `storage_analysis`
- [ ] Add pure helpers in `legacy_report_data.py` (no API):
  - `derive_repo_consumers(repo_actions, errors, *, limit=5, max_repos, truncated) -> dict`
  - `derive_artifact_storage(storage_analysis, *, max_repos, truncated) -> dict`
  - `derive_release_assets(storage_analysis, *, max_repos, truncated) -> dict`
- [ ] Implement `build_legacy_report_data(api, username, *, max_repos=100, warn_over=None) -> dict`:
  1. Fetch `account`, `rate_limits`; compute legacy `api_estimate`; quota guard
  2. Fetch repos once via `report_data._limited_repos`
  3. Fetch `repo_actions` (+ per-repo errors), `storage_analysis`, `actions_os_breakdown`, `billing_history`
  4. **Derive** `repo_consumers`, `artifact_storage` (and `release_assets` when enabled) — no `get_repo_consumers` / `get_artifact_storage_details` / `get_release_asset_details`
  5. Reuse `report_data` helpers for account-level sections (`get_actions_usage`, `get_copilot_usage`, `get_gitlfs_usage`, `get_monthly_costs`, `get_key_insights`, `get_warning_state`) without calling full `build_report_data` (avoids re-entering consumer/artifact fetch paths)
  6. Return merged superset dict
- [ ] **Test:** `tests/test_legacy_report_data.py` — all expected keys; `repo_actions` row count; derived `repo_consumers` matches sort of `repo_actions`; derived `artifact_storage` matches `storage_analysis` fixture
- [ ] **Test:** `FakeAPI` request counter — for N repos, artifact endpoint called **N times**, not **2N** (storage + derived artifact_storage)
- [ ] **Test:** per-repo billing failure on one repo does not abort build; error appears in `repo_consumers.errors` or shared errors map

---

## Phase 2 — Terminal Render Layer

Split renderers across existing section modules to respect the ~500-line file limit:

- [ ] For each `show_*` in `report_account.py`, `report_actions.py`, `report_products.py`, `report_summary.py`:
  - Extract printing logic into `render_*` that accepts dict slices (no `api`).
  - **Keep every `show_*` as a deprecated public wrapper** — either fetch+`render_*` for backward compat, or delegate to `render_*` when given pre-fetched data. **Do not delete** `show_*` or remove from `src/github_usage/legacy.py` re-exports (`tests/test_legacy_compat.py`).
- [ ] Add `legacy_terminal.py` with `render_legacy_report(data: dict) -> None` mirroring `_run_report_body` section order:
  1. Account + rate limits (after `print_header` in session helper — preserve order)
  2. Actions → repos → OS → Copilot → LFS → monthly costs → billing history → limits → base costs → final summary → what else → footer
- [ ] Handle `errors` sections gracefully in render (short error line when section is `None` and `errors[key]` is set).
- [ ] **Test:** `tests/test_legacy_terminal.py` — `legacy_report_data.json` → stdout golden substring checks
- [ ] **Test:** Port progress-bar overflow test to `render_*` path if `show_final_summary` internals move

---

## Phase 3 — Wire CLI, `legacy_report.main`, and GUI Backend

- [ ] Add `run_legacy_report_session(…)` in `legacy_report.py` (137 lines today — room for orchestration; **reduces `cli.py`** which is at 420 lines with an advisory warning):
  1. Resolve token, validate scope
  2. `print_header()`
  3. `data = build_legacy_report_data(api, username, …)`
  4. `render_legacy_report(data)`
  5. Return `(0, data, username)` for export
- [ ] Refactor `_run_legacy_report` in `cli.py`:
  - Replace `legacy_main()` + second `build_report_data()` with session helper
  - Export uses the **same** `data`; remove duplicate `GitHubAPI` for export
- [ ] Update `legacy_report.main()` to use session helper; preserve keyword-only signature and `str | None` return for compatibility
- [ ] **Mandatory:** Update `gui_backend.run_legacy_report_data` to call `build_legacy_report_data` instead of `build_report_data` so CLI and TUI exports share the **same superset schema**
- [ ] **Test:** `tests/test_legacy_single_fetch.py` — request counter on `cli.main(["--export", "json", …])`; each billing path once per repo
- [ ] **Test:** Update `tests/test_export_cli.py` and `tests/test_gui_reports.py` for unified data path
- [ ] **Test:** `tests/test_legacy_compat.py` still passes

---

## Phase 4 — Cleanup & Size Compliance

- [ ] Remove `_run_report_body` API-fetching loop once `render_legacy_report` is live
- [ ] Convert `show_*` internals to thin wrappers around `render_*` (remove duplicate fetch logic from wrappers used by legacy path; wrappers may still fetch for external one-off callers)
- [ ] **Do not** remove `show_*` symbols or `legacy.py` re-exports
- [ ] Run `scripts/check-sizes`; confirm `cli.py` line count **decreased**, all modules stay **under 400 lines** (hard limit 500)
- [ ] Grep for stale imports of removed private helpers

---

## Phase 5 — Documentation & Close-out

- [ ] `CHANGELOG.md` — `[Unreleased]` → **Changed**: legacy CLI + export single-fetch; lower API usage; CLI and TUI legacy export share superset schema
- [ ] `README.md` — brief note under “Exporting Reports” if user-visible
- [ ] Remove Fix #2 item from `TO_DO.md`; link to archived plan
- [ ] Set banner to `> **Status:** COMPLETE` (colon **outside** bold per `AGENTS.md`) and move to `docs/superpowers/plans/archived/`

---

## Verification

- [ ] `scripts/check` — unit tests, smoke, sizes (`cli.py` advisory cleared or reduced)
- [ ] `scripts/smoke` — legacy `--cli` and export paths
- [ ] `scripts/docs-check`
- [ ] Manual (optional, live token): `github-usage --cli --export json --no-interactive` — terminal sections + valid export JSON

---

## Risks & Mitigations

| Risk | Mitigation |
| :--- | :--- |
| Terminal output drift | Golden heading/substring tests; one manual diff before merge |
| Hidden duplicate artifact/release fetches | **Derive** `artifact_storage` / `release_assets` from `storage_analysis` only (Phase 1 requirement) |
| Hidden duplicate per-repo Actions fetches | **Derive** `repo_consumers` from `repo_actions` only (Phase 1 requirement) |
| `get_monthly_costs` triple-fetches billing summaries | Accept for this plan; follow-up optimization |
| Export schema breakage | Keep existing export keys; add new keys only |
| `legacy.py` / external `show_*` callers break | Preserve `show_*` as deprecated wrappers; keep re-exports |
| CLI vs TUI export schema drift | **Mandatory** `gui_backend` → `build_legacy_report_data` |
| Under-estimated quota guard | Legacy-specific `api_estimate` formula + tests |

---

## Suggested Implementation Order

1. Phase 1 — `legacy_report_data.py`, derive helpers, fixture, counter tests
2. Phase 2 — `render_*` + `legacy_terminal.py` + stdout tests
3. Phase 3 — CLI session, `gui_backend`, single-fetch integration test
4. Phases 4–5 — wrapper cleanup, sizes, docs

**Estimated touch surface:** `legacy_report_data.py` (new), `legacy_terminal.py` (new), `legacy_report.py`, `cli.py`, `gui_backend.py`, `report_*.py`, `storage.py` (read-only reuse), `tests/test_legacy_*.py` (new), `tests/_fakes.py`, `tests/test_export_cli.py`, `tests/test_gui_reports.py`
