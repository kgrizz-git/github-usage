# [2026-06-19 02:35] Implementation Plan — Remaining Bug Report Items

This plan addresses the items still open after the work captured in
[`2026-06-16-bug-fixes.md`](2026-06-16-bug-fixes.md) and the staleness review
at the top of
[`../../assessments/bug-report-20260616-143630.md`](../../assessments/bug-report-20260616-143630.md).

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development
> (recommended) or superpowers:executing-plans to implement this plan task-by-task.
> Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close out the three partially-fixed bugs and the three still-open
bugs from the original report, with tests added for each. No live API calls
per `AGENTS.md`; all new tests use fake tokens, mocks, and fixtures.

**Tech Stack:** Python standard library, `unittest`, `unittest.mock`.

---

## Tasks

### Phase 1: High Priority (correctness)

- [ ] **#20 — `_generated_line` prints `Generated: None`**
  - **File:** `src/github_usage/email_report.py`
  - **Problem:** `format_report_email` calls
    `_generated_line(str(data.get("generated_at", "")))`. When callers pass
    `generated_at=None`, `str(None)` becomes the literal string `"None"`,
    `datetime.fromisoformat("None")` raises `ValueError`, and the `except`
    branch returns `f"Generated: None"`. When `generated_at` is `""`, the
    same path returns `f"Generated: "` with a stray trailing space.
  - **Change:** Make `_generated_line` treat a falsy or unparseable
    `generated_at` as "use today's UTC date" rather than reflecting the
    raw input. Drop the `str(...)` wrap at the call site and pass the
    value through unchanged.
  - **Validation:** Add tests in `tests/test_email_report.py` covering:
    - `generated_at=None` → output contains a current-date prefix and does
      not contain the literal string `None`.
    - `generated_at=""` → same.
    - `generated_at="not-an-iso-string"` → falls back to today's date.
    - `generated_at="2026-06-15T14:30:00Z"` → unchanged behaviour.
  - **Verify:** `bash scripts/check`.

- [ ] **#8 — `check_user_scope` rejects fine-grained PATs and GitHub Apps**
  - **File:** `src/github_usage/auth.py`
  - **Problem:** The check reads the deprecated `X-OAuth-Scopes` header,
    which fine-grained PATs and GitHub Apps do not emit. A valid token
    with `/user` access returns `False`, so callers print a misleading
    "missing 'user' scope" message and the user is sent down the wrong
    remediation path.
  - **Change:** Replace the `X-OAuth-Scopes` parse with a scope-agnostic
    check. Use `GET /user/installations` (or the rate-limit response
    from the existing `api` instance) to verify the token is accepted
    on a user-scoped endpoint, and only fall back to the legacy header
    for classic PATs when the response is 200 and the header is present.
    Keep the existing `try/finally: conn.close()` and the
    `if resp.status != 200: return False` guard.
  - **Validation:** Add tests in `tests/test_auth.py` covering:
    - Token works (200 from `/user/installations`) → returns `True`.
    - 401 from the probe → returns `False`.
    - Connection is closed on both paths (mocked `HTTPSConnection`).
  - **Verify:** `bash scripts/check`.

- [ ] **#18 — `sys.argv` mutation is process-global**
  - **Files:** `src/github_usage/cli.py` (`_resolve_email_token`,
    `_run_legacy_report`).
  - **Problem:** Both call sites save and restore `sys.argv`, but the
    mutation is not thread-safe. Library users running under
    `concurrent.futures` or with a signal handler that inspects
    `sys.argv` can see torn state. `finally` only helps for the common
    case.
  - **Change:** Stop mutating `sys.argv`. Add an explicit `argv`
    parameter to `resolve_token` (defaulting to `None`, in which case
    it falls back to `sys.argv[1:]` to preserve the existing public
    behaviour). Have `_resolve_email_token` and `_run_legacy_report`
    pass the explicit argv slice to `resolve_token` directly.
  - **Validation:** Add tests in `tests/test_auth.py` and
    `tests/test_cli.py` covering:
    - `resolve_token(argv=["fake-token"])` returns `"fake-token"`
      without reading `sys.argv`.
    - `resolve_token(argv=None)` reads from `sys.argv` (legacy path).
    - Calling `_resolve_email_token()` does not mutate `sys.argv`
      (assert `sys.argv` is unchanged before/after).
  - **Verify:** `bash scripts/check` and `bash scripts/smoke`.

### Phase 2: Medium Priority (finish partial fixes)

- [ ] **#12 — `try/except SystemExit` around `legacy_main`**
  - **File:** `src/github_usage/cli.py`
  - **Problem:** `_run_legacy_report` still wraps the `legacy_main`
    call in `try/except SystemExit` (line 337-338). The literal
    `ValueError` from `int(exc.code or 0)` is fixed by `_safe_exit_code`,
    but the broad `except` still swallows any `SystemExit` raised inside
    the legacy flow, including ones from nested test harnesses.
  - **Change:** Let `parser.parse_args` propagate `SystemExit` directly
    (keep the `_safe_exit_code` translation only for the parse step).
    For the `legacy_main` call, only catch `SystemExit` when the legacy
    flow has been refactored to use `return` instead of `sys.exit(...)`
    for user-visible errors; until then, narrow the catch so test
    harnesses that intentionally raise `SystemExit` propagate through.
    Concretely: remove the `try/except` around `legacy_main` and rely
    on the legacy flow returning exit codes via `sys.exit`, then
    surface that exit code at the top-level `main()` boundary instead.
  - **Validation:** Add a test in `tests/test_cli.py` asserting that
    `parser.error` from a bad flag (e.g. `cli.main(["--max-repos",
    "foo"])` on the email subcommand) returns a non-zero code with
    the argparse error message on stderr and does not raise.
  - **Verify:** `bash scripts/check` and `bash scripts/smoke`.

- [ ] **#16 — `int()` raises on non-numeric size values**
  - **File:** `src/github_usage/report_optional.py`
  - **Problem:** `int(item.get("size_in_bytes") or 0)` and
    `int(asset.get("size") or 0)` now handle `None` and missing keys,
    but still raise `ValueError` when the API returns a non-integer
    such as a string `"1024.5"` or a `float`.
  - **Change:** Wrap the size conversion in a small helper that tries
    `int()` and falls back to `0` (skipping the item) on
    `ValueError`/`TypeError`. Apply to both the artifacts and
    release-asset paths.
  - **Validation:** Add tests in `tests/test_export_report.py` (or a
    new `tests/test_report_optional.py`) covering:
    - `size_in_bytes="1024"` (numeric string) → parsed.
    - `size_in_bytes="abc"` → item skipped, repo still aggregated.
    - `size_in_bytes=1024.7` → item skipped.
    - `size_in_bytes=None` → still skipped (regression).
  - **Verify:** `bash scripts/check`.

### Phase 3: Low Priority (nice-to-haves)

- [ ] **#19 — Static `User-Agent` string**
  - **File:** `src/github_usage/api.py`
  - **Note:** This was a Low/suggestion-only item. Optional. If
    addressed, set the `User-Agent` to
    `f"github-usage-report/{__version__} (+https://github.com/...)"` in
    the `GitHubAPI` constructor.
  - **Verify:** `bash scripts/check`.

- [ ] **Test coverage: remaining untested modules**
  - The bug report's coverage gap section is now substantially closed,
    but a few entry points are still untested. Add minimal smoke tests:
    - `auth.check_user_scope` (covered by the #8 tests above).
    - `report_data.get_key_insights`.
    - `report_optional.get_repo_consumers` and
      `get_release_asset_details`.
  - **Verify:** `bash scripts/check`.

- [ ] **Stale fixture files in `tests/fixtures/`**
  - `artifacts.json`, `billing_actions_summary.json`,
    `billing_copilot_summary.json`, `billing_git_lfs_summary.json`,
    `premium_request_usage.json`, `rate_limit.json`, `releases.json`
    are still on disk and not referenced by any test. Either wire
    them into the new tests added above or delete them to keep
    `tests/fixtures/` truthful.
  - **Verify:** `bash scripts/check`; `rg -l
    'artifacts\.json\|releases\.json\|premium_request_usage\.json\|rate_limit\.json'
    tests/` should be empty afterwards (or list the tests that now
    consume them).

---

## Done criteria

A phase is done when:
1. The relevant unit tests pass (`bash scripts/check`).
2. The CLI still starts (`bash scripts/smoke`).
3. The new behaviour is exercised by at least one test using mocks or
   fixtures (no live GitHub API calls).
4. No real tokens, raw API responses, or generated billing reports are
   added to the repo.

## Out of scope

- Any rewrites larger than what's needed to close the listed bugs.
- Refactoring of legacy flow that is not directly required by #12.
- Historical-month billing work (deferred per
  [`../../assessments/bug-report-20260616-143630.md`](../../assessments/bug-report-20260616-143630.md)
  and `docs/api-discovery-month.md`).
