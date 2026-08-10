# Fix: Email report forecast should use private-only quota inputs

> **Status:** IN PROGRESS

## Problem

The email report forecast projects total Actions minutes (private + public) against the 2,000-minute free-tier limit. Only private repos consume quota — public repos are free. The legacy terminal report handles this correctly; the email report does not.

The consumers section already shows a private/public breakdown (computed independently from per-repo data in `get_repo_consumers()`), but the **account-level** visibility split is missing from `report["actions"]`. This affects:

| Section | What it reads | Impact |
|---|---|---|
| Forecast scope note | `"public_minutes" in forecast` | No "(private repos — quota-counted)" label |
| Key Insight 1 | `actions["private_minutes_percent"]` | Insight silently dropped when >=100% |
| Warning threshold | Prefers `private_minutes_percent`, falls back to `minutes_percent` | Evaluates against total (private+public) |
| Text actions sub-line | `"public_minutes" in actions` | Private/public breakdown not shown |

## Root Cause

`report_data.build_report_data()` (the email path) fetches account-level billing via `get_actions_usage()` which returns combined private+public minutes, then never calls `attach_actions_visibility_split()` to reconcile the per-repo split into account-level private/public aggregates.

The legacy path (`legacy_report_data.build_legacy_report_data()`) correctly calls `attach_actions_visibility_split()` at line 326, which adds `private_minutes`, `public_minutes`, `private_minutes_percent`, etc. to `report["actions"]`.

## Files Involved

- `src/github_usage/report_data.py` — `build_report_data()` (line 319) — **missing the split call**
- `src/github_usage/legacy_report_data.py` — `build_legacy_report_data()` (line 326) — **has the call (reference)**
- `src/github_usage/usage_split.py` — `attach_actions_visibility_split()` (line 282) — requires `repo_actions` list
- `src/github_usage/report_forecast_data.py` — `_private_quota_inputs()` (line 17) — fallback logic when split is absent
- `src/github_usage/report_data.py` — `get_key_insights()` (line 203) — insight 1 depends on `private_minutes_percent`
- `src/github_usage/report_data.py` — `get_warning_state()` (line 155) — threshold prefers `private_minutes_percent`
- `src/github_usage/email_report_html.py` — forecast rendering (line 345) — checks `"public_minutes" in forecast`
- `src/github_usage/email_report_text.py` — actions section (line 47) — checks `"public_minutes" in actions`
- `src/github_usage/report_optional.py` — `get_repo_consumers()` (line 25) — already fetches per-repo data; needs to expose raw rows
- `src/github_usage/report_actions.py` — `fetch_repo_actions_table()` (line 172) — returns `(rows, errors)` tuple, used by legacy path

## Recommendation

Add a call to `attach_actions_visibility_split()` in `build_report_data()` after `_fetch_sections()` returns and before `get_key_insights()` / `get_warning_state()`. The split needs per-repo Actions billing data (`repo_actions`) as its second argument.

### Approach: hybrid — reuse consumers rows when available, fetch separately otherwise

Two code paths feed the split, depending on whether consumers are enabled:

1. **`include_consumers=True`** — `get_repo_consumers()` already calls `get_actions_per_repo()` for every repo (`report_optional.py:35`) and builds rows with `repo`, `minutes`, `storage_avg_mb`, and `visibility` — the same shape `attach_actions_visibility_split()` needs. Extend `get_repo_consumers()` to return its raw rows under a `_raw_rows` key (or a dedicated public key), then pass them directly to `attach_actions_visibility_split()`. This avoids duplicating every per-repo API call.

2. **`include_consumers=False`** — `get_repo_consumers()` is not called, so no rows are available. Call `fetch_repo_actions_table(api, repos)` from `report_actions.py:172`, which returns `(rows, errors)` — the same function the legacy path uses.

### Prerequisite: ensure `repos` is populated when `include_actions=True`

Currently `build_report_data()` only fetches repos when `needs_repos = include_consumers or include_artifact_storage or include_release_assets` (line 338). When `include_actions=True` alone, `repos` is `[]` and the split has nothing to iterate. Fix: add `include_actions` to `needs_repos` so repos are always available when the split is needed. (The legacy path always fetches repos, so this is consistent.)

### Recommended call-site ordering

`build_report_data()` computes `report["insights"]` and `report["warnings"]` immediately after `_fetch_sections()` returns (lines 395-396), and both `get_key_insights()` (reads `private_minutes_percent`) and `get_warning_state()` (prefers `private_minutes_percent`, falls back to `minutes_percent`) consume the split keys. The `attach_actions_visibility_split()` call must therefore be inserted **after** `actions` is populated by `_fetch_sections()` and **before** the insights/warnings lines — i.e., between line 393 and line 395 in `report_data.py`. Placing it inside `_fetch_sections()` is acceptable too, but it must run before those two consumers read `report["actions"]`. Failing to honor this ordering silently leaves the bug in place even after "adding the call."

### Scope note: `include_actions=False`

`attach_actions_visibility_split()` already no-ops when `report["actions"]` is `None` (usage_split.py:296-297), so the call is safe to add unconditionally. However, the per-repo Actions fetch (path 2 above) should be skipped when `include_actions=False`, since the split has nothing to attach to.

### API cost note

When `include_consumers=True`, approach 1 reuses the consumers' existing per-repo calls — zero extra API cost. When `include_consumers=False`, approach 2 adds one API call per repo (same as the legacy path). For users with `max_repos=100`, this is up to 100 additional calls. This is acceptable and consistent with the legacy path's behavior.

## Tasks

- [ ] Expand `needs_repos` in `build_report_data()` to include `include_actions` so repos are always fetched when the split is needed
- [ ] Extend `get_repo_consumers()` in `report_optional.py` to return raw per-repo rows (e.g. `_raw_rows` key) for reuse by the split
- [ ] Add `attach_actions_visibility_split()` call to `build_report_data()` in `report_data.py`, using consumers raw rows when available, falling back to `fetch_repo_actions_table()` when not
- [ ] Verify `get_key_insights()` and `get_warning_state()` need no changes (they already handle the fallback correctly — the fix just ensures the split keys are present)
- [ ] Add test: email report path with `include_consumers=True` reuses consumer rows for the split (no duplicate API calls)
- [ ] Add test: email report path with `include_actions=True` and `include_consumers=False` uses `fetch_repo_actions_table()` for the split
- [ ] Add test: `include_actions=False` skips the per-repo fetch entirely
- [ ] Run `scripts/check` and `scripts/smoke`
- [ ] Update CHANGELOG.md

## Verification

1. Generate an email report and confirm the forecast section shows "(private repos — quota-counted)" label
2. Confirm Key Insight 1 appears when private minutes >= 100%
3. Confirm the text actions section shows the private/public sub-line
4. Confirm the warning threshold evaluates against private-only minutes
5. Confirm the consumers section still works correctly (it should be unaffected)
6. Confirm the email path with `include_actions=True` and `include_consumers=False` shows the split (exercises the `fetch_repo_actions_table()` fallback path)
7. Confirm no duplicate per-repo API calls when `include_consumers=True` (the consumers' existing calls are reused for the split)
