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
    raw input. Update the function's type hint from `generated_at: str`
    to `generated_at: str | None` to match the new contract. Drop the
    `str(...)` wrap at the call site and pass the value through
    unchanged.
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
    check. A 200 from `GET /user` already proves the token is accepted
    on a user-scoped endpoint, so `check_user_scope` should just return
    `True` on status 200 and `False` on any non-200. Do not probe
    `/user/installations` — that endpoint is restricted to GitHub Apps
    and org-owned fine-grained PATs, and would also return 404 for
    personal fine-grained PATs. Keep the existing
    `try/finally: conn.close()` and the `if resp.status != 200: return False`
    guard. The duplicate `GET /user` calls in `_run_email_report`
    (line 242 and the one inside `check_user_scope`) are left in place
    for this fix — collapsing them requires either changing the
    `check_user_scope(api)` signature to accept a pre-fetched response,
    or refactoring it to use `api.request()`, and either change is scope
    creep. Address in a follow-up if `check_user_scope` is shown to be
    a hot path.
  - **Error message updates:** After the semantic change from
    scope-based to acceptability-based, update the misleading
    "Your GitHub token is missing the 'user' scope" / "the billing
    endpoints require the 'user' scope" / "gh auth refresh ... -s user"
    messages at the following call sites so they no longer point
    users at a scope that no longer exists:
    - `cli.py:248-251` (the `_run_email_report` check) — replace with
      a generic "Your GitHub token is not valid for this operation"
      and drop the "gh auth refresh ... -s user" remediation.
    - `legacy_report.py:58-61` (the legacy flow's check) — same
      replacement. Without this, the legacy path will still print the
      misleading message, leading to inconsistent CLI output.
    - `legacy_report.py:63-76` (the diagnostic block that prints
      "Current token scopes:" by making a second raw `http.client`
      `/user` call with legacy `Authorization: token {token}` auth).
      With the new scope-agnostic check, the "Current token scopes"
      diagnostic is no longer meaningful (the new check ignores the
      `X-OAuth-Scopes` header entirely) and the second call only runs
      when the first one already returned False, so the diagnostic
      will print nothing useful. **Delete this block.**
    - `api.py:57-64` (the 404-on-billing-endpoint hint) — drop the
      "missing the 'user' scope" wording and the "gh auth refresh ...
      -s user" remediation, but keep the 404 context. Suggested
      replacement: "This usually means your token does not have access
      to this billing endpoint." Leave the setup_wizard.py prompts
      that mention "user scope" in user-facing labels alone — those
      are input prompts, not error messages, and are out of scope.
  - **Validation:** Add tests in `tests/test_auth.py` covering:
    - Token works (200 from `/user`, no `X-OAuth-Scopes` header) →
      returns `True` (covers fine-grained PATs and GitHub Apps).
    - Classic PAT with `X-OAuth-Scopes: user,repo` and 200 from `/user`
      → still returns `True` (regression for classic PATs).
    - 401 from the probe → returns `False`.
    - Connection is closed on both paths (mocked `HTTPSConnection`).
  - **Verify:** `bash scripts/check` and `bash scripts/smoke` (the
    error-message change is a user-visible CLI output change).

- [ ] **#18 — `sys.argv` mutation is process-global**
  - **Files:** `src/github_usage/cli.py` (`_resolve_email_token`,
    `_run_legacy_report`).
  - **Problem:** Both call sites save and restore `sys.argv`, but the
    mutation is not thread-safe. Library users running under
    `concurrent.futures` or with a signal handler that inspects
    `sys.argv` can see torn state. `finally` only helps for the common
    case.
  - **Change:** Stop mutating `sys.argv`. Add an explicit `argv`
    parameter to `resolve_token` (which currently has no parameters at
    `auth.py:20`), defaulting to `None`, in which case it falls back to
    `sys.argv[1:]` to preserve the existing public behaviour. Have
    `_run_legacy_report` pass the explicit argv slice to `resolve_token`
    directly. This must thread through every call site, including the
    two `resolve_token()` calls inside `_run_legacy_report`
    (cli.py:320 — the pre-`legacy_main` check — and cli.py:341 — the
    post-`legacy_main` re-resolve for the export block), so neither
    call needs the mutated `sys.argv` to be in scope. **Delete
    `_resolve_email_token` (cli.py:116-122)** — once `resolve_token`
    takes an `argv` argument, the only thing this wrapper does is
    call `resolve_token(argv=["github-usage"])`, which is a one-liner
    at the single call site (`_run_email_report` cli.py:222). Inline
    that call and remove the wrapper; per `AGENTS.md` "Avoid
    unnecessary complexity: prefer readable, straightforward code
    over clever or overly generic solutions."
  - **Validation:** Add tests in `tests/test_auth.py` and
    `tests/test_cli.py` covering:
    - `resolve_token(argv=["fake-token"])` returns `"fake-token"`
      without reading `sys.argv`.
    - `resolve_token(argv=None)` reads from `sys.argv` (legacy path).
    - Calling `_resolve_email_token()` does not mutate `sys.argv`
      (assert `sys.argv` is unchanged before/after).
    - `_run_legacy_report` flow does not mutate `sys.argv` across the
      whole call (use a sentinel argv and assert it is unchanged
      after `cli.main(["ghp_fake_token", "--json"])` returns).
  - **Verify:** `bash scripts/check` and `bash scripts/smoke`.

### Phase 2: Medium Priority (finish partial fixes)

- [ ] **#12 — `try/except SystemExit` around `legacy_main`**
  - **File:** `src/github_usage/cli.py`
  - **Problem:** `_run_legacy_report` still wraps the `legacy_main`
    call in `try/except SystemExit` (line 337-338). The literal
    `ValueError` from `int(exc.code or 0)` is fixed by `_safe_exit_code`,
    but the broad `except` still swallows any `SystemExit` raised inside
    the legacy flow, including ones from nested test harnesses.
  - **Change:** Remove the `try/except SystemExit` around `legacy_main`.
    `legacy_main` already uses `sys.exit(...)` for user-visible errors,
    so `SystemExit` will propagate naturally. Wrap the **entire body
    of `main()`** (cli.py:374 — currently no top-level try/except) in a
    single `try/except SystemExit` that converts the exit to a return
    code via `_safe_exit_code`. Keep the `_safe_exit_code` translation
    in the two `parse_args` call sites (cli.py:195 in `_run_email_report`
    and cli.py:301 in `_run_legacy_report`) so argparse errors (e.g.
    bad `--max-repos foo`) still return a non-zero code instead of
    propagating `SystemExit`.
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
  - **Change:** Introduce a small private module-level helper
    `_safe_int_size(value)` in `src/github_usage/report_optional.py`
    that returns `None` on `ValueError`/`TypeError` and the parsed
    `int` otherwise (treating `None`/missing as `None`, not `0`).
    Replace the `sum(int(item.get("size_in_bytes") or 0) for ...)`
    expression in `get_artifact_storage_details` and the analogous one
    in `get_release_asset_details` with a pattern that excludes `None`
    values from the sum, e.g.
    `sum(s for s in (_safe_int_size(item.get("size_in_bytes")) for item in artifacts) if s is not None)`.
    Items with non-numeric or missing sizes are skipped (not added as 0
    to the per-repo total), and a per-repo total of 0 after the filter
    still means the repo is omitted from `top_repos` via the existing
    `if size:` guard.
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
    `f"github-usage-report/{__version__} (+https://github.com/kgrizz-git/github-usage)"`
    in the `GitHubAPI` constructor (current value is the static
    `"github-usage-report-v3"`). Note: `api.py` does not currently
    import `__version__`; add `from . import __version__` (or
    `from .__init__ import __version__`) at the top of the file as
    part of this change.
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
    `premium_request_usage.json`, `rate_limit.json`, `releases.json`,
    `repos.json`, `user.json` are still on disk and not referenced by
    any test. (`email_report_data.json` and `export_report_data.json`
    are referenced by `tests/test_email_report.py` and
    `tests/conftest.py`/`tests/test_export_cli.py` respectively and
    should stay.) Either wire the unreferenced fixtures into the new
    tests added above or delete them to keep `tests/fixtures/` truthful.
  - **Verify:** `bash scripts/check`. To detect stale fixtures
    reliably, list every file in `tests/fixtures/` and confirm each
    one appears in at least one `tests/**/*.py` reference (direct
    string match on the filename is sufficient — the codebase loads
    fixtures via `Path(...) / "name.json"`, so a simple
    `rg -l '<filename>' tests/` per-file check is the canonical
    verification; do not rely on a single combined regex).

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
