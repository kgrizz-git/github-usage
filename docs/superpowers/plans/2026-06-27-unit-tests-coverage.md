> **Status:** IN PROGRESS — **NEEDS REVIEW**
>
> **DO NOT MERGE** until review is complete. This plan is submitted for discussion.

**Date:** 2026-06-27

## Objective

Improve unit test coverage for the remaining uncovered or minimally covered code paths in `github-usage`:
1. `src/github_usage/report_account.py` (rate limits, account info, and product references).
2. `src/github_usage/report_summary.py` (top consumers, storage breakdown, impactful findings, recommendations, and orchestrator).
3. `src/github_usage/billing.py` (workflow runs billing, full billing parsing, and per-repo API queries).

This ensures robust validation and helps maintain the code health of the CLI report rendering layers.

## Current State & Coverage Gaps

- **`report_account.py`**: Minimal coverage (only one basic test for `show_account_info`). Needs coverage for standard/premium rate limit parsing, missing/zero/null rate limit bounds, plan formatting details, missing plan keys, and special character username URL formatting.
- **`report_summary.py`**: Untested helpers (`_print_top_consumers`, `_print_storage_breakdown`, `_print_impactful_findings`, `_print_recommendations`) and main orchestrator. Carries a cosmetic bug where raw storage (GB) is printed using `fmt_price` (leading to output like `$0.5000` instead of `0.5000 GB`). Sibling modules (`report_products.py` and `report_actions.py`) have been audited and verified correct.
- **`billing.py`**: Needs tests for `get_full_billing` error/success paths, a defensive check for non-dict API responses (ensuring consistent `None` return values), error/empty returns in `get_actions_per_repo`, and date pinning / empty/malformed returns in `get_actions_from_runs`. The test suite also carries an incorrect comment claiming a bug in workflow minute accumulation.

## Definition of Done

- All new tests are implemented using standard `unittest` library and mocks.
- `scripts/check` and `scripts/docs-check` run successfully and pass all stages.
- Code conforms to lint and formatting guidelines (`ruff check` and `ruff format --check`).
- No live network requests are made during tests (must use mocks and fakes).
- The matching item is removed from `TO_DO.md` upon completion.

## Proposed Implementation Plan

### Phase 0: Test Infrastructure Cleanup
- Extract `FakeAPI` from `tests/test_billing.py` and move it to `tests/_fakes.py`. Update `tests/test_billing.py` and new test suites to import `FakeAPI`.

### Phase 1: `report_account.py` Bug Fixes & Unit Tests
- **Bug Fix:** Modify `show_rate_limits` in `src/github_usage/report_account.py` so that if `remaining` or `limit` is explicitly `None` in the API payload, it falls back to `"?"` (e.g. `rem = r.get("remaining") if r.get("remaining") is not None else "?"`).
- Add tests to `tests/test_report_account.py`:
  - `test_show_rate_limits_formats_standard_resources`: Mock `/rate_limit` response with custom limits and verify standard API sections and reset timestamps are formatted correctly in stdout.
  - `test_show_rate_limits_formats_premium_tiers`: Mock `/rate_limit` resources with limits > 5000 and confirm premium output displays them with percentage calculations. Ensure standard rate limit resources are not duplicated.
  - `test_show_rate_limits_handles_missing_or_null_remaining`: Verify that missing keys or explicit `None` (null) `remaining` values default to `"?"`, but a `0` remaining value prints `0` and does not print `"?"`.
  - `test_show_account_info_handles_space_limit_conversions`: Verify space fields convert correctly from bytes to GB when numeric (integer/float), format correctly when non-numeric/zero, and behave correctly under negative space scenarios.
  - `test_show_account_info_includes_optional_plan_details`: Verify collaborators and private repo limits print only when present.
  - `test_show_account_info_missing_plan_key`: Mock `/user` response lacking a `plan` key to verify it is handled gracefully and the plan block is skipped.
  - `test_show_what_else_prints_expected_help`: Assert standard info prints as expected via `assertIn` on key stable substrings. Use a username with special characters (e.g. `octo-cat`) to verify formatting.

### Phase 2: `report_summary.py` Bug Fixes & Unit Tests
- **Bug Fix:** Modify `src/github_usage/report_summary.py` to format storage numbers as GB strings using `f"{val:.4f} GB"` instead of `fmt_price(val)` at the following locations:
  - Inside `_print_storage_breakdown` for repository total storage.
  - Inside `_print_storage_breakdown` for top consumer repository total storage.
  - Inside `_print_storage_breakdown` for item-level storage.
  - Inside `_print_impactful_findings` for the biggest storage consumer total storage.
  - Inside `_print_recommendations` for release assets usage description.
- Add tests to `tests/test_report_summary.py`:
  - `test_print_top_consumers_sorts_correctly`: Feed sample repo data and verify top 5 repositories are ordered correctly by minutes and cost.
  - `test_print_top_consumers_zero_and_none_edgecases`: Verify no crash/division errors occur when `user_minutes` or `actions_gross` is `0`, `0.0`, or `None`, and confirm `premium_by_model` works correctly with `{}` or `None`.
  - `test_print_top_consumers_formats_copilot_and_lfs`: Supply model-level premium usage and LFS data to verify request rate summaries and SKU-level billing amounts match calculations.
  - `test_print_storage_breakdown_renders_details`: Verify top 10 repos list is printed, and verify specific breakdown lines (type, count, storage size) are printed. Test with missing/empty `"repos"` key in `storage_analysis`.
  - `test_print_impactful_findings_selects_top_three`: Confirm when >3 findings are generated, only the top 3 are printed. Test boundary conditions (GB vs MB conversion, zero/none edge cases for minutes and cost, cost per minute). Verify division guard when `actions_gross` is 0. Verify no crash with negative `user_minutes` (e.g. `-1.0`).
  - `test_print_recommendations_triggers_specific_rules`: Construct inputs targeting self-hosted runner rule (top 2 repos > 70%), Copilot model consolidation rule (>2 models), and large release assets warning. Verify recommendation is skipped if `repo_data` has 0 or 1 repos, or if `user_minutes` is `0` or negative. Verify default recommendations path when no rules fire.
  - `test_print_recommendations_release_assets_boundary`: Assert boundary for release assets (exactly `0.1` GB should not trigger, `0.1001` GB should).
  - `test_show_final_summary_calls_all_subsections`: Integration test asserting the orchestrator coordinates sub-functions. Mock `api.request` for the premium request usage endpoint path. Verify it handles cases where `copilot_summary` and `lfs_summary` are `None`.

### Phase 3: `billing.py` Cleanup, Bug Fixes & Function Tests
- **Cleanup:** Remove the misleading comment describing a non-existent bug on lines 152–153 in `tests/test_billing.py`.
- **Bug Fix (`get_actions_from_runs`):** Change `billable.get(os_name, {}).get("millis", 0)` in `src/github_usage/billing.py` to `(billable.get(os_name) or {}).get("millis", 0)` to handle runs where `billable` contains an OS key mapped to `None`.
- **Defensive Check (`get_full_billing`):** Check if `data` is a dictionary. If not, return `None` (consistently returning the same sentinel as other error paths).
- Add tests to `tests/test_billing.py`:
  - `test_get_actions_from_runs_sends_correct_dates`: Pin the `date` class to a static date (e.g. `2026-06-15`) using `@mock.patch('github_usage.billing.date')` and verify the `created` filter parameter passed to `get_all_pages` is `2026-06-01..2026-06-30`.
  - `test_get_actions_from_runs_handles_missing_fields`: Mock runs lacking `billable`, containing `billable` keys mapped to `None`, or lacking `workflow_name` to confirm default values are used safely.
  - `test_get_actions_from_runs_empty`: Test function output when run list is empty. Assert return value matches default initialized values `(0.0, {"UBUNTU": 0, "WINDOWS": 0, "MACOS": 0}, {})`.
  - `test_get_actions_from_runs_os_millis`: Verify OS millisecond accumulator logic works correctly.
  - `test_get_full_billing_success`: Mock `/settings/billing/usage` returning valid list of billing items.
  - `test_get_full_billing_failure`: Mock API client raising `RuntimeError` and assert function returns `None`.
  - `test_get_full_billing_nondict`: Mock API client returning a non-dict response (e.g. list `[1, 2]` or string `"ok"`) and assert function returns `None`.
  - `test_get_actions_per_repo_error_propagation`: Verify client `RuntimeError` raises `BillingFetchError`.
  - `test_get_actions_per_repo_empty_response`: Verify return value `(0.0, 0.0, {})` when response is empty/null.

### Phase 4: Verification
- Run format and lint checks:
  - `ruff check`
  - `ruff format --check`
- Run unit tests with coverage (if coverage tool is available) to verify gaps are closed:
  - `coverage run -m unittest discover -s tests`
  - `coverage report`
- Run local verification checks:
  - `./scripts/check`
  - `./scripts/docs-check`
