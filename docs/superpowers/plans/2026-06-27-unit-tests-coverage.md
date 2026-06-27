> **Status:** IN PROGRESS — **NEEDS REVIEW**
>
> **DO NOT MERGE** until review is complete. This plan is submitted for discussion.

**Date:** 2026-06-27

## Objective

Improve unit test coverage for the remaining uncovered or minimally covered code paths in `github-usage`:
1. `src/github_usage/report_account.py` (rate limits, account info, and product references).
2. `src/github_usage/report_summary.py` (top consumers, storage breakdown, impactful findings, recommendations, and orchestrator).
3. `src/github_usage/billing.py` (workflow runs billing, full billing parsing, and per-repo API queries).

## Current State & Coverage Gaps

- **`report_account.py`**: Minimal coverage (only one basic test for `show_account_info`). Needs coverage for standard/premium rate limit parsing, missing/zero/null rate limit bounds, plan formatting details, missing plan keys, and special character username URL formatting. Both `show_rate_limits` and `show_account_info` call `.get()` on the API response without checking that the response is a dict.
- **`report_summary.py`**: Untested helpers (`_print_top_consumers`, `_print_storage_breakdown`, `_print_impactful_findings`, `_print_recommendations`) and main orchestrator. Carries a cosmetic bug where raw storage (GB) is printed using `fmt_price` (leading to output like `$0.5000` instead of `0.5000 GB`). Also carries a class of latent `TypeError`/`ValueError` bugs in comparisons, additions, and f-string formatters when contract-defined `None` values are passed.
- **`billing.py`**: Needs tests for `get_full_billing` error/success paths, a defensive check for non-dict API responses (ensuring consistent `None` return values), error/empty returns in `get_actions_per_repo`, and date pinning / empty/malformed returns in `get_actions_from_runs`. The same non-dict-returned-by-API shape exists in `get_billing_summary`, `get_premium_request_usage`, and `get_actions_per_repo` and should be hardened in the same PR. The test suite also carries a stale comment (`tests/test_billing.py:152`) claiming a workflow-minute accumulation bug that was fixed in a prior PR (see CHANGELOG "Workflow Over-counting" under `### Fixed`).

## Definition of Done

- All new tests implemented using standard `unittest` and `unittest.mock`. No live network requests.
- `ruff check` and `ruff format --check` pass (run these *before* `scripts/check` so a lint failure is not hidden behind a test pass).
- `./scripts/check` and `./scripts/docs-check` pass.
- A `CHANGELOG.md` entry is added under `[Unreleased] → ### Fixed` covering the user-visible output change in `_print_storage_breakdown` and `_print_recommendations` (storage is now displayed in GB instead of as a dollar amount) and the latent `None` guard tightening. This PR is bug-fix-only; a version bump is deferred to the next release tag.
- The matching item is removed from `TO_DO.md` upon completion.

## Proposed Implementation Plan

### Phase 0: Test Infrastructure Cleanup

Consolidate the four duplicated `FakeAPI` classes into `tests/_fakes.py` (which already exists and contains `FakeSleeper` and `assert_monotonic_increasing`). Use a single class with optional `request` and `get_all_pages` (each defaulting to a sensible empty response) so the four call sites can use the same class. Add a module-level docstring and a class docstring per `AGENTS.md`.

| File | Class name | Methods |
|---|---|---|
| `tests/test_billing.py:4` | `FakeAPI` | `request`, `get_all_pages` |
| `tests/test_report_data.py:4` | `FakeAPI` | `request`, `get_all_pages` |
| `tests/test_storage.py:5` | `FakeAPI` | `get_all_pages` only |
| `tests/test_report_optional.py:12` | `_FakeAPI` | `get_all_pages` only |

Update all four test files plus the new `tests/test_report_account.py` and `tests/test_report_summary.py` to import `FakeAPI` from `tests._fakes`.

### Phase 1: `report_account.py` Bug Fixes & Unit Tests

**Bug Fix — None-safety across `show_rate_limits` and `show_account_info`:** Both functions call `.get()` on an API response without checking the response is a dict. Both also have `r.get(key, default)` patterns that don't handle explicit `None` (only missing keys). Apply the following guards (use `or 0` / `is None` per the existing project style — the project favors readable code over inline ternaries):

| Site | Current | Fix |
|---|---|---|
| `show_rate_limits:13` — non-dict response | `data = api.request(...); resources = data.get("resources", {})` | `if not isinstance(data, dict): data = {}` before `.get` |
| `show_rate_limits:14` — `resources` non-dict | `resources = data.get("resources", {})` | `if not isinstance(resources, dict): resources = {}` after the `.get` |
| `show_rate_limits:24` — standard tier `r` non-dict | `r = resources.get(key, {})` | `if not isinstance(r, dict): r = {}` after the `.get` |
| `show_rate_limits:25-26` — standard `remaining` and `limit` | `rem = r.get("remaining", "?")`, `lim = r.get("limit", "?")` | `is None` guard for both (preserves `0`) |
| `show_rate_limits:39` — premium tier `res` non-dict | `for name, res in resources.items()` | `if not isinstance(res, dict): continue` (skip non-dict resources) |
| `show_rate_limits:40` — premium tier `limit` and `used` | `limit = res.get("limit", 0); used = res.get("used", 0)` | `is None` guard for both (preserves `0`) |
| `show_account_info:51` — non-dict response | `user = api.request(...); user.get("login", "?")` | `if not isinstance(user, dict): user = {}` before `.get` |
| `show_account_info:54` — `plan` non-dict | `plan = user.get("plan", {})` | `if not isinstance(plan, dict): plan = {}` after the `.get` (the existing `if plan:` truthy check then skips the whole plan block) |

`reset_ts` in the standard tier is already None-safe via the `if reset_ts:` truthy check.

**Tests in `tests/test_report_account.py`:**
- `test_show_account_info_prints_pro_plan_happy_path` — baseline: `plan` populated with `name`, numeric `space` in bytes, `collaborators`, `private_repos`; each formatted line is asserted.
- `test_show_account_info_returns_username_and_type` — return tuple matches `("octocat", "User")`.
- `test_show_account_info_handles_non_dict_user_response` — `/user` returns `None`; no raise; returns `("?", "?")`.
- `test_show_rate_limits_handles_non_dict_response` — `/rate_limit` returns `None`; no raise; empty standard-tier output.
- `test_show_rate_limits_handles_non_dict_resources` — `/rate_limit` returns `{"resources": null}` or `{"resources": "junk"}`; no raise; empty output.
- `test_show_rate_limits_handles_non_dict_resource_entry` — a resource key (e.g. `{"core": null}`) is mapped to `None`; no raise; the standard tier prints `"?"` for that resource.
- `test_show_rate_limits_handles_non_dict_premium_entry` — a premium-tier resource value is `None` or a non-dict; no raise; the entry is skipped (no crash on `res.get(...)`).
- `test_show_account_info_handles_non_dict_plan` — `/user` returns `{"plan": null}` or `{"plan": "free"}`; no raise; the plan block is skipped (existing `if plan:` truthy check now also handles non-dict because the fix coerces to `{}`).
- `test_show_rate_limits_formats_standard_resources` — standard sections and reset timestamps render correctly.
- `test_show_rate_limits_formats_premium_tiers` — resources with `limit > 5000` render with percentage; standard tiers not duplicated.
- `test_show_rate_limits_handles_missing_or_null_remaining` — missing keys or `None` for `remaining` or `limit` default to `"?"`; a `0` value prints `0`.
- `test_show_rate_limits_handles_null_limit_in_premium_tier` — `{"limit": None, "used": <nonzero>}` resource is silently skipped.
- `test_show_rate_limits_handles_null_used_in_premium_tier` — `{"used": None, "limit": <nonzero>}` resource is silently skipped (would otherwise crash the `used / limit` and `{used:>6}` format on line 44).
- `test_show_account_info_handles_space_limit_conversions` — bytes→GB for numeric, omitted for `0`/`False`/`None`; **negative** `int`/`float` prints as `"-0.0 GB available"` (not verbatim — the `isinstance(space, int | float)` branch always runs the bytes-to-GB conversion regardless of sign); a negative string like `"-100"` would print verbatim. The current code does no input validation.
- `test_show_account_info_includes_optional_plan_details` — collaborators and private_repos print only when present.
- `test_show_account_info_missing_plan_key` — missing `plan` key is skipped gracefully.
- `test_show_what_else_prints_expected_help` — `assertIn` on 3-5 stable substrings; `octo-cat` username renders literal URL (no encoding).

### Phase 2: `report_summary.py` Bug Fixes & Unit Tests

**Bug Fix — storage formatting (`$0.5000` → `0.50 GB`):** Replace `fmt_price(val)` with `f"{val:.2f} GB"` at:
- `_print_storage_breakdown` for repository total (top-10 list).
- `_print_storage_breakdown` for top consumer repository total.
- `_print_storage_breakdown` for item-level storage.
- `_print_recommendations` for release assets usage.

Use `.2f` to match the existing GB formatter at `_print_impactful_findings:230` (do not introduce a new precision).

**Bug Fix — redundant size in `_print_impactful_findings:232`:** The current line `findings.append(f"Biggest storage consumer: {top_st['name']} at {fmt_price(top_st['total_storage'])} ({size_str})")` produces redundant output (`at 0.50 GB (512 MB)`) because `size_str` is already a `f"{total_gb:.2f} GB"` or `f"{total_gb * 1024:.0f} MB"` string from line 230. Drop the duplicate and use `size_str` alone: `findings.append(f"Biggest storage consumer: {top_st['name']} ({size_str})")`. The corresponding test must assert the finding text contains `size_str` and does **not** contain a `$`.

**Bug Fix — None-tolerance across `report_summary.py`:** The contract is that `user_minutes`/`user_storage_gb_hours`/`actions_gross`/`actions_discount`/`actions_net` may be `None`. The following sites raise `TypeError` (or `ValueError` for f-string) on `None`; apply `or 0` coalescing at each:

| Site | Operation | Risk |
|---|---|---|
| `show_final_summary:32-34` | `+` (orchestrator math) | `None + int` raises before any helper runs |
| `_print_top_consumers:91` | `> 0` (`actions_gross`) | Comparison fails |
| `_print_impactful_findings:241` | `> 0` (`total_discount`, `total_gross`) | Comparison fails |
| `_print_impactful_findings:246` | `> 0` (`total_net`, `user_minutes`) | Comparison fails |
| `_print_recommendations:272` | `> 0` (`user_minutes`) | Comparison fails |
| `_print_utilization:168` | `{user_minutes:>8.1f}` | f-string format fails (Python allows `f"{None}"` but not `f"{None:.1f}"`) |

The companion storage line at `_print_utilization:183` is already None-safe via `gb_hours_to_avg_mb(...) if user_storage_gb_hours else 0`. The call site in `legacy_report.py:69-81` is not changed in this PR.

**Tests in `tests/test_report_summary.py`:**
- `test_print_top_consumers_sorts_correctly` — top 5 repos ordered by minutes and cost; input/expected in docstring.
- `test_print_top_consumers_zero_and_none_edgecases` — `user_minutes`/`actions_gross` safe for `0`, `0.0`, `None`; `premium_by_model` safe for `{}`/`None`.
- `test_print_top_consumers_formats_copilot_and_lfs` — concrete `premium_by_model` (one model, two items, mixed prices) and `lfs_summary` payloads; assert `@/req` and `@/ea` lines and totals.
- `test_print_storage_breakdown_renders_details` — top 10 repos printed; breakdown lines printed; missing/empty `"repos"` key handled; storage values use `X.XX GB` (no `$`).
- `test_print_storage_breakdown_storage_uses_gb_suffix` — regression: no `$`, `GB` suffix present.
- `test_print_impactful_findings_selects_top_three` — seed all six findings to exercise the cap unambiguously; boundary conditions (GB vs MB, zero/none/negative, cost per minute, `actions_gross=0`).
- `test_print_impactful_findings_handles_none_totals` — regression: each of `user_minutes`/`actions_gross`/`total_discount`/`total_gross`/`total_net` `None` individually does not raise.
- `test_print_recommendations_triggers_specific_rules` — self-hosted runner rule (top 2 > 70%), Copilot consolidation (>2 models), release assets rule; skipped for 0/1 repos or `user_minutes <= 0`; default path when no rules fire.
- `test_print_recommendations_release_assets_boundary` — `0.1` GB does not trigger, `0.1001` GB does; text contains `0.10 GB`.
- `test_print_utilization_handles_none_user_minutes` — regression: `user_minutes=None` does not raise; prints `0.0`.
- `test_show_final_summary_handles_none_orchestrator_math` — regression: `actions_gross`/`actions_discount`/`actions_net` all `None` does not raise.
- `test_show_final_summary_calls_all_subsections` — integration: `copilot_summary`/`lfs_summary` `None` handled; `user_minutes`/`user_storage_gb_hours`/`actions_gross` `None` handled.

### Phase 3: `billing.py` Cleanup, Bug Fixes & Function Tests

**Cleanup:** Remove the misleading comment at `tests/test_billing.py:152` that claims the workflow-minute accumulator is buggy. The accumulator in `billing.py:145-146` is correct (`workflow_minutes.get(wf_name, 0) + run_minutes`) — the comment is a stale remnant of the bug fixed in a prior PR (CHANGELOG "Workflow Over-counting"). The CHANGELOG line itself remains accurate; only the test comment is stale.

**Bug Fix — `get_actions_from_runs`:** Change `billable.get(os_name, {}).get("millis", 0)` to `(billable.get(os_name) or {}).get("millis", 0)` to handle runs where `billable` contains an OS key mapped to `None`. Without this, `{"UBUNTU": None}.get("millis", 0)` raises `AttributeError`.

**Bug Fix — non-dict defensive check across 4 billing functions:** The same shape exists in `get_billing_summary`, `get_premium_request_usage`, `get_full_billing`, and `get_actions_per_repo`. Each public function must return the documented empty-sentinel (`None` for the first three, `(0.0, 0.0, {})` for `get_actions_per_repo`) when the API returns a non-dict. `get_user_actions_billing` uses `get_billing_summary` and inherits the guard transitively.

A `_usage_items(data)` module-private helper (mirroring the pattern at `report_data.py:47`) makes the safe item access explicit, but the helper is **not** a substitute for the public-function-level `isinstance` check — it is a secondary safety net for the `data.get` call:

```python
def _usage_items(data):
    """Return ``data['usageItems']`` when ``data`` is a dict, else ``[]``."""
    return data.get("usageItems", []) if isinstance(data, dict) else []
```

Add explicit `isinstance(data, dict)` early returns (returning the documented sentinel) **before** the helper call in each of the four functions. For `get_full_billing` and `get_actions_per_repo`, both `if not data` and `isinstance` checks are needed (different "no data" conditions: `data == 0` and `data == []` are also "no data").

**Bug Fix — None values inside item dicts (sanitize at the source):** The `isinstance` check above protects against a non-dict *top-level* response, but the same shape exists *inside* individual item dicts. `item.get("grossAmount", 0)` returns `None` (not `0`) when the key exists but the value is JSON `null`; `float(item.get("grossAmount", 0.0))` then raises `TypeError` (because `float(None)` is invalid). Per-site `or 0` coalescing is brittle because the items dicts are stored in `summary["items"][sku] = item` (and `sku_breakdown[sku] = item`) and read by downstream callers in `legacy_report.py:34-36`, `report_actions.py:26-28` and `:50`, `report_products.py:33-35`/`:89-91`/`:128-130`/`:232`/`:250`/`:272`/`:291`, and `report_summary.py:121` — none of which can be safely enumerated and updated in this PR.

Instead, add a single source-sanitization helper in `src/github_usage/report_helpers.py`:

```python
def sanitize_item_amounts(item: dict) -> dict:
    """Return a copy with grossAmount/discountAmount/netAmount/grossQuantity None replaced by 0.0."""
    sanitized = dict(item)
    for key in ("grossAmount", "discountAmount", "netAmount", "grossQuantity"):
        if sanitized.get(key) is None:
            sanitized[key] = 0.0
    return sanitized
```

Apply it at the *storage* site in each accumulator function (where the raw item is stored in the returned `items` / `sku_breakdown` dict). The `+=` and `qty = ...` lines that read the same item can then drop their `or 0` / `float(...)` coalescing — the items are guaranteed non-None:

| File | Function | Storage site (apply `sanitize_item_amounts` here) |
|---|---|---|
| `billing.py` | `get_billing_summary` | `summary["items"][sku] = item` |
| `billing.py` | `get_premium_request_usage` | `by_model[m]["items"].append(item)` |
| `billing.py` | `get_actions_per_repo` | `sku_breakdown[sku] = item` |
| `report_data.py` | `_billing_summary` | `summary["items"][sku] = item` |
| `report_data.py` | `get_copilot_usage` | The `premium` loop's `entry["items"].append(item)` *or* an equivalent aggregate — see implementation |
| `report_optional.py` | `get_repo_consumers` | `rows.append({... "gross": sum(...), ...})` (sanitize the items before summing so the `sum` is over a clean list) |

After this fix, all downstream consumers (legacy_report, report_actions, report_products, report_summary) can trust the items and need **no changes** in this PR. They may still use `item.get("X", 0)` defensively, but those defaults are now only hit when the key itself is missing — never when the value is `null`.

**Bug Fix — additional `isinstance` checks in `report_data.py`:** The Phase 3 `_usage_items` helper and the `isinstance(data, dict)` early-returns cover four billing functions, but `report_data.py` has two more direct `api.request` call sites that do `(response or {}).get(...)` without first checking that the response is a dict. If the API returns a list, string, or other non-dict, `.get` raises `AttributeError`:

- `report_data.get_copilot_usage:93-97` — `premium = api.request(...); for item in (premium or {}).get("usageItems", []):` → add `if not isinstance(premium, dict): premium = {}` before the `.get`. Without this, the `premium` loop on line 104-107 cannot run at all on a malformed response, even though the `_billing_summary` path above it was hardened.
- `report_data._rate_limit:208-214` — `data = api.request("GET", "/rate_limit"); core = (data or {}).get("resources", {}).get("core", {})` → add `if not isinstance(data, dict): data = {}` after the `.request` call. `build_report_data` uses `_rate_limit` to check remaining quota, so a malformed rate-limit response must not crash the whole report build.

**Bug Fix — `get_actions_from_runs` defensive empty-list default:** In `src/github_usage/billing.py:130`, `runs = api.get_all_pages(...)` is followed by `for run in runs:`. If `api.get_all_pages` returns `None` (e.g. an error path that the test mock didn't anticipate), the loop raises `TypeError: 'NoneType' object is not iterable`. Add `runs = runs or []` (or `if not runs: return default_values` for an early exit) before the loop. The existing `test_get_actions_from_runs_empty` test exercises the `[]` case; a new test should exercise the `None` case.

**Tests in `tests/test_billing.py`:**
- `test_get_actions_from_runs_sends_correct_dates` — pin `date` to `2026-06-15`; assert `created` filter is `2026-06-01..2026-06-30`. The mock must return a real `date` (not `MagicMock`) so the chained `.replace()` calls produce a real `date`. Use `mock.patch.object(billing, "date")` and assign a real `date(2026, 6, 15)` to `.today.return_value`. Also assert the request path is `/repos/{owner}/{repo}/actions/runs` so the test still exercises the wiring if the date-pinning is later refactored.
- `test_get_actions_from_runs_handles_missing_fields` — runs lacking `billable`, `billable` keys mapped to `None`, or missing `workflow_name`; after the fix, `billable == {"UBUNTU": None}` must not raise.
- `test_get_actions_from_runs_empty` — empty run list; assert `(0.0, {"UBUNTU": 0, "WINDOWS": 0, "MACOS": 0}, {})`. Trivially passes today (loop body is skipped); serves as a regression marker.
- `test_get_actions_from_runs_os_millis` — multi-OS and per-OS totals.
- `test_get_full_billing_success` — `/settings/billing/usage` returns valid list.
- `test_get_full_billing_failure` — `RuntimeError` raised; function returns `None`.
- `test_get_full_billing_nondict` — list or string response; function returns `None`.
- `test_get_billing_summary_nondict` — non-dict response; returns `None`.
- `test_get_billing_summary_handles_null_amounts` — item with `{"grossAmount": null, "discountAmount": null, "netAmount": null}`; the stored item dict has `0.0` in those keys, and totals stay `0.0` instead of raising `TypeError` on `+= None`. Verifies the source sanitization in `billing.get_billing_summary`.
- `test_get_premium_request_usage_nondict` — non-dict response; returns `None`.
- `test_get_premium_request_usage_handles_null_amounts` — item with null `grossQuantity`/amount fields; per-model totals stay `0.0` and the stored item list contains sanitized entries.
- `test_get_actions_per_repo_nondict` — non-dict response; returns `(0.0, 0.0, {})`.
- `test_get_actions_per_repo_handles_null_quantity` — item with `"grossQuantity": null`; `total_minutes`/`total_storage_gb_hours` stay `0.0` and the stored SKU dict has `grossQuantity=0.0`.
- `test_get_actions_usage_handles_null_amounts` (in `test_report_data.py`) — items with null amount fields; `report_data._billing_summary` sanitizes before storage; the public `get_actions_usage` result's `sku_breakdown` values have `0.0` in the null fields. Regression for `report_data.py:58-60` and `:71`.
- `test_get_copilot_usage_handles_null_amounts` (in `test_report_data.py`) — items in both the `_billing_summary` Copilot path and the inline `premium` loop with null amount fields; `by_model` entries have `0.0` for null fields. Regression for `report_data.py:104-107`.
- `test_get_repo_consumers_handles_null_gross` (in `test_report_optional.py`) — per-repo SKU with `"grossAmount": null`; aggregated `gross` stays `0.0` and the SKU dict (if exposed) has `0.0`. Regression for `report_optional.py:39`.
- `test_get_actions_per_repo_error_propagation` — `RuntimeError` raises `BillingFetchError`.
- `test_get_actions_per_repo_empty_response` — empty/null response; returns `(0.0, 0.0, {})`.
- `test_get_actions_from_runs_handles_none_response` — `api.get_all_pages(...)` returns `None` (not `[]`); after the fix, function returns the default `(0.0, {"UBUNTU": 0, "WINDOWS": 0, "MACOS": 0}, {})` instead of raising `TypeError`.
- `test_get_copilot_usage_handles_non_dict_premium` (in `test_report_data.py`) — `/premium_request/usage` returns a list or string; `get_copilot_usage` does not raise and returns a dict with empty `by_model`.
- `test_rate_limit_handles_non_dict_response` (in `test_report_data.py`) — `/rate_limit` returns a list; `_rate_limit` returns `(None, None)` instead of raising `AttributeError`.

### Phase 4: Verification

- `ruff check` and `ruff format --check` (run first so a lint failure is not hidden behind a test pass).
- Optional: `coverage run -m unittest discover -s tests` and `coverage report` to verify gaps are closed.
- `./scripts/check` and `./scripts/docs-check`.
- `scripts/smoke` is **not** required — this PR does not change the CLI entrypoint.
- No `pyproject.toml` changes needed (`unittest` and `unittest.mock` are stdlib).
- After the PR is merged, **the developer must** (per `AGENTS.md` § Documentation Lifecycle — not optional):
  1. Move this file to `docs/superpowers/plans/archived/`. (`scripts/docs-check` warns but does not fail on this; the move is still required.)
  2. Update the status banner to the canonical form `> **Status:** COMPLETE` (colon outside the bold), appending the merge commit SHA on the same line (e.g. `> **Status:** COMPLETE (merged in <sha>)`).
  3. Do not leave the plan in `docs/superpowers/plans/` after merge — canonical form is "archived + COMPLETE + commit noted."
