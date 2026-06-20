# [2026-06-19 03:00] Implementation Plan — Default API/Resend Timeout & Retry + CLI Overrides

This plan addresses the open `TO_DO.md` item on line 22:

> Add default GitHub API and Resend timeout/retry behavior, then consider
> `--timeout SECONDS` and `--max-retries N` flags if users need control.

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development
> (recommended) or superpowers:executing-plans to implement this plan task-by-task.
> Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make outbound HTTP calls to `api.github.com` and `api.resend.com`
predictable in the face of transient network failures by giving them
sensible default timeouts and retry behavior, and surface that behavior to
users through `--timeout SECONDS` and `--max-retries N` flags on both the
legacy `github-usage` and the `github-usage email-report` subcommands.

**Tech Stack:** Python standard library (`http.client`, `urllib.error`,
`socket`), `unittest`, `unittest.mock`. No new third-party dependencies.

**Out of scope:**
- Backoff jitter / decorrelated jitter (we use a bounded, additive
  exponential backoff — see "Design notes" below).
- Circuit breakers or adaptive throttling.
- Surfacing retry counters in user-facing output (the existing
  `RuntimeError` chain already surfaces the final failure).
- Changes to the `--month` or `--email-format html` workstreams.

---

## Pre-Implementation Work (do these first, in one prep commit if possible)

These items are pre-requisites for the main plan. They either fix design
flaws the main plan inherited from the current code, or extract small
utilities that the main plan depends on. Doing them first turns the main
plan into a much smaller, less error-prone change.

- [ ] **P1 — Decide the 403 / Retry-After policy before writing tests.**
  The current `api.py:52-57` branch retries 403+`Retry-After` and the new
  helper will retry 408/429/5xx+`Retry-After`. The main plan kept the old
  branch "preserved unchanged" — that creates a double-retry counter
  (helper max_retries=3 + outer `_retries < 3` cap) and the tests in
  Phase 1 will keep needing special-case scaffolding to avoid it.
  Adopt the following policy and write the policy into a one-paragraph
  comment block in `src/github_usage/http_retry.py`:
    - The helper retries any status in `RETRYABLE_STATUSES` (408, 429,
      500, 502, 503, 504) when `Retry-After` is present or the status
      itself is retryable. It does **not** retry 403, 404, or any other
      4xx.
    - The 403+`Retry-After` branch in `api.py` is **deleted**. Callers
      that depended on the 403+`Retry-After` retry get a
      `RuntimeError("API error 403: ...")` instead. The CLI's
      `check_user_scope` already does a 200-only check, so the 403
      branch was only ever reachable from the user-error path; no
      production code path loses retry coverage by deleting it.
    - Document the decision in this plan's "Done" note.

- [ ] **P2 — Change `legacy_report.main` signature to accept `timeout` /
  `max_retries` keywords.**
  Removes the need for the `GITHUB_USAGE_TIMEOUT` /
  `GITHUB_USAGE_MAX_RETRIES` env-var indirection proposed in the original
  Phase 2. The env-var approach had three problems: (a) `os.environ.setdefault`
  silently overwrites a user-set value, (b) it's invisible in `--help`,
  and (c) tests have to assert on `os.environ` state rather than on
  observable behavior.
  - **File:** `src/github_usage/legacy_report.py`
  - **Change:** add `timeout: float | None = None` and
    `max_retries: int | None = None` to the `main(...)` signature. Pass
    them to the `GitHubAPI(token, ...)` constructor on line 54.
  - **File:** `src/github_usage/cli.py:317` — add the two keyword args
    to the `legacy_main(...)` call site in `_run_legacy_report`.
  - **Tests:** existing `test_legacy_compat.py` still passes (new
    keywords are optional). Add a tiny unit test asserting that
    `GitHubAPI(...)` is constructed with the passed values.
  - **Done when:** `bash scripts/check` passes; this commit has no
    observable behavior change (defaults propagate through unchanged).

- [ ] **P3 — Move `auth.check_user_scope` to use `api.request`.**
  `src/github_usage/auth.py:57` opens its own raw
  `https.client.HTTPSConnection("api.github.com")` and is the third
  HTTP client site in the codebase (after `api.py` and `email_report.py`).
  Leaving it untouched means `check_user_scope` will continue to hang on
  a stalled socket even after the main plan lands.
  - **File:** `src/github_usage/auth.py`
  - **Change:** rewrite `check_user_scope(api, user=None)` so that
    the API object passed in is the only HTTP caller. If `user` is
    supplied (a dict already returned from `api.request("GET", "/user")`),
    `check_user_scope` validates that dict (must have a non-empty
    `login` field) and returns `True`/`False` without making a
    second HTTP call. If `user` is `None`, it falls back to
    `api.request("GET", "/user")`, catches `RuntimeError`, and
    returns `True` on a 200 with a `login` field, `False`
    otherwise. The function signature is extended with the
    optional `user` kwarg; the no-arg form still works.
  - **Caller updates (avoid duplicate `/user` calls):**
    - `src/github_usage/cli.py:_run_email_report` already calls
      `api.request("GET", "/user")` at line 233 to get
      `username`. After P3, it must pass that dict into
      `check_user_scope(api, user=user)` instead of letting
      `check_user_scope` make a second `/user` call. (See
      acceptance criteria; the duplicate-call review finding
      would otherwise burn an extra API request per email
      report.)
    - `src/github_usage/legacy_report.py:main` calls
      `check_user_scope(api)` at line 57 without a prior `/user`
      fetch in the legacy path. The fallback (no-arg) form
      applies here, and `legacy_main` does not need to change
      beyond what P2 already does.
  - **Tests:** existing `test_auth.py` covers the True/False paths;
    confirm they still pass and add tests that:
    - a transport-level `RuntimeError` returns `False` (no raise);
    - `check_user_scope(api, user={"login": "octocat"})` returns
      `True` without calling `api.request` (mock and assert
      `api.request` was not called);
    - `check_user_scope(api, user={})` returns `False` without
      calling `api.request`.
  - **Done when:** the only `HTTPSConnection` call sites in the package
    are `api.py` and `email_report.py` (verify with
    `rg "HTTPSConnection" src/`), and `_run_email_report` no longer
    triggers two `/user` calls per run.

- [ ] **P4 — Add `parse_retry_after` utility.**
  - **File:** `src/github_usage/http_retry.py` (new, with the helper
    from Phase 1)
  - **Signature:**
    ```python
    def parse_retry_after(header_value: str | None) -> int | None:
        """Return the integer seconds from a Retry-After header, or None."""
    ```
  - **Behavior:** strip whitespace; return `None` for `None`, empty,
    or non-integer input. Used by the helper and (defensively) by any
    future caller that wants to inspect a `Retry-After` value.

- [ ] **P5 — Add a `FakeSleeper` test helper.**
  - **File:** `tests/_fakes.py` (new)
  - **Public surface:** a class with a `calls: list[float]` attribute
    and a `__call__(seconds: float) -> None` method that appends
    `seconds` to `calls`. Used by `test_http_retry.py`,
    `test_api.py`, and `test_email_report.py` to assert monotonic
    backoff without `time.sleep`.
  - Include a one-line `assert_monotonic_increasing` helper for the
    common assertion pattern.

- [ ] **P6 — Verify `scripts/smoke` covers `email-report --help`.**
  The current `scripts/smoke` only exercises
  `github-usage --help` and `--version`. After Phase 2 adds
  `--timeout` / `--max-retries` to the email parser, the smoke
  script should verify the new flags appear in
  `github-usage email-report --help` output.
  - **File:** `scripts/smoke`
  - **Change:** add `PYTHONPATH=src scripts/python -m github_usage
    email-report --help | grep -q -- "--timeout"` (and `--max-retries`).
  - **Done when:** removing the flag from `_email_parser` makes the
    smoke script fail; restoring it makes it pass.

- [ ] **P7 — Note `cli.py` will exceed 400 lines after Phase 2.**
  `src/github_usage/cli.py` is currently 374 lines. Adding 2 flags +
  validation + plumbing to both parsers pushes it to ~420.
  `AGENTS.md` Code Style says to start splitting at 400.
  - **Action:** extract `_legacy_parser` and `_email_parser` (and
    their supporting constants) into a new
    `src/github_usage/cli_parsers.py` module. Import them back into
    `cli.py`. No behavior change.
  - **Done when:** `cli.py` is back under 400 lines and
    `bash scripts/check` passes.

- [ ] **P8 — Repoint existing test patches at the new helper module.**
  Once Phase 1 moves the live `HTTPSConnection` call into
  `github_usage.http_retry`, every test that currently patches
  `http.client.HTTPSConnection` at the call site will fail because
  the call site no longer exists there. This must land **as part
  of Phase 1**, not after it, otherwise the first
  `bash scripts/check` run will go red.
  - **Affected tests (verified):**
    - `tests/test_api.py` — lines 14, 31, 45, 73, 90 patch
      `github_usage.api.http.client.HTTPSConnection`. Two of these
      also reach into `_last_link` (lines 106, 109); those
      assertions need to be replaced with `Link` set on the
      mock response's `headers.get(...)` instead of
      `api._last_link = ...`, because the helper now owns the
      header capture (see "Wire the helper into `GitHubAPI`"
      below).
    - `tests/test_email_report.py` — lines 89, 104 patch
      `github_usage.email_report.http.client.HTTPSConnection`.
    - `tests/test_auth.py` — lines 95, 113, 131 patch
      `http.client.HTTPSConnection` via `mock.patch.object` on
      the imported module. After P3, `auth.py` no longer
      imports `http.client`, so these patches must be
      rewritten to patch
      `github_usage.api.http.client.HTTPSConnection` (or to
      mock `GitHubAPI.request` directly).
  - **Recommended approach:** patch
    `github_usage.http_retry.http.client.HTTPSConnection` in
    `test_api.py` and `test_email_report.py`; in `test_auth.py`,
    either mock `GitHubAPI.request` to return a fake response
    or patch the new connection location. Patching
    `request_with_retries` itself is the cleanest long-term
    approach for the new tests.
  - **Done when:** all three test files pass against the
    refactored `api.py` / `email_report.py` / `auth.py`, and
    `bash scripts/check` is green.

---

## Background

### Current state of the two HTTP clients

`src/github_usage/api.py` (89 lines) defines `GitHubAPI`:

- `GitHubAPI.__init__(self, token)` takes only a token. It builds an
  `http.client.HTTPSConnection("api.github.com")` per request.
- `GitHubAPI.request` opens a connection, sends the request, and
  reads the response. It has **no socket timeout** — a stalled
  connection will block the CLI indefinitely.
- It has one ad-hoc retry path: `resp.status == 403` and the response
  carries a `Retry-After` header. The hard-coded retry count is
  `_retries < 3`, with a sleep of `reset + 1` seconds. All other
  failures raise immediately. There is no retry on 429, 5xx, or
  transport-level errors (connection reset, DNS, `URLError`,
  `socket.timeout`). **(This 403 branch is removed in Pre-Implementation
  P1; the helper absorbs 408/429/5xx+`Retry-After`.)**
- `GitHubAPI.get_all_pages` loops pages of an endpoint. There is no
  per-page backoff for 429s outside the embedded 403 path (which is
  the only path the 403 branch can actually reach from the docs).

`src/github_usage/email_report.py` (198 lines) defines `send_email`:

- Opens `http.client.HTTPSConnection("api.resend.com")` per call.
- **No socket timeout**, **no retry** on any status code. The only
  retry-friendly status (429) is treated as a hard error via the
  generic "status not in (200, 201)" branch.
- A 5xx from Resend aborts the email send with no recovery.

`src/github_usage/auth.py` (66 lines) defines `check_user_scope`:

- Opens its **own** raw `https.client.HTTPSConnection("api.github.com")`
  (line 57), completely bypassing `GitHubAPI`. **(Migrated to use
  `api.request` in Pre-Implementation P3 so it inherits the new
  timeout/retry behavior automatically.)**

### Why we need defaults

- A stalled socket on a flaky VPN / corporate proxy currently hangs
  the report (or the email, or the `check_user_scope` call) with no
  signal to the user.
- A transient 502/503/504 from GitHub or Resend aborts the whole run.
  The current 403/Retry-After path is the only safety net and only
  fires for the rate-limit abuse case.
- 429 ("Too Many Requests") responses are not retryable in the current
  code at all.

### Design notes

- **Defaults.** Use a 30-second connect+read timeout and a maximum of
  3 retries (i.e. up to 4 total attempts) for both clients. These are
  the values the bug report effectively assumed when it mentioned
  "default … timeout/retry behavior" and they match the existing 403
  retry depth of 3. Override only the parts that users actually need
  to change. Worst-case wall time for 3 retries with the chosen
  backoff: each of the 4 attempts can hit the 30s timeout, and the
  3 inter-attempt sleeps are `1 + 2 + 4 = 7s`, giving
  `4 × 30 + 7 ≈ 127s` per call before the final `RuntimeError` —
  worth mentioning in the README so users understand the time
  budget. (Earlier draft had `1 + 2 + 4 + 8 + 16 + 30 + 30 ≈ 91s`,
  which used the wrong number of sleep terms; the corrected math
  above is what the implemented code will actually do.)
- **Retry trigger set.** Retry on:
  - network / transport errors (`http.client.RemoteDisconnected`,
    `http.client.ResponseNotReady`, `socket.timeout`,
    `ConnectionResetError`, `ConnectionRefusedError`),
  - HTTP `429` and `5xx` responses,
  - HTTP `408` (Request Timeout).
  Honor `Retry-After` (header, integer seconds) when present;
  otherwise back off exponentially: `2 ** attempt` seconds, capped at
  30s. Do not retry on `401`, `403`, `404`, or any other 4xx.
  (Per Pre-Implementation P1: the existing 403+`Retry-After` branch
  is removed; 403 is treated as a hard error, same as 401/404.)
- **Flag scope.** Add `--timeout SECONDS` and `--max-retries N` to
  both `_legacy_parser` and `_email_parser`. A negative
  `--max-retries` is a user error. `--timeout 0` is translated
  internally to `None` (the stdlib "no timeout" sentinel) so
  users get the documented "block forever" behavior. The CLI
  rejects negative `--timeout` at parse time as well.
  Validate at parse time.
- **Where the retry loop lives.** A small `request_with_retries`
  helper in `http_retry.py` (the only retry code path). The public
  `GitHubAPI.request` signature does not change.
- **Plumbing for the legacy parser.** Per Pre-Implementation P2,
  `legacy_report.main` accepts optional `timeout` / `max_retries`
  keyword args. `_run_legacy_report` threads them through the
  `legacy_main(...)` call. No env vars are used as a control channel.
- **What is intentionally not changing.** The `Link` header handling
  in `get_all_pages` is preserved by having the helper expose the
  raw `http.client.HTTPMessage` (which is case-insensitive via
  `.get("Link", "")`) on the `Response` dataclass, rather than a
  case-folded `dict[str, str]`. The `Link` header is no longer
  cached on `self._last_link`; `get_all_pages` reads it from the
  `Response` returned by each `request()` call.
- **Where `from __future__ import annotations` is required.**
  `http_retry.py` uses `int | None` and `str | None` in signatures.
  Python 3.11 (the project's minimum) does support PEP 604 unions
  at runtime, so the import is not strictly required for those
  annotations. The import is kept anyway for consistency with the
  other modules in the package (every existing `src/github_usage/`
  module starts with `from __future__ import annotations`).

---

## Tasks

### Phase 1: Add timeout/retry helpers

- [ ] **Extract a shared retry helper into a new module.**
  - **File:** `src/github_usage/http_retry.py` (new)
  - **Why new file:** `AGENTS.md` (Code Style) says to keep files and
    functions small; both `api.py` and `email_report.py` will gain
    retry logic, and a shared helper avoids drift.
  - **Public surface:**
    ```python
    from __future__ import annotations

    import http.client
    import socket
    import time
    from collections.abc import Callable
    from dataclasses import dataclass

    DEFAULT_TIMEOUT_SECONDS = 30
    DEFAULT_MAX_RETRIES = 3
    DEFAULT_MAX_BACKOFF_SECONDS = 30
    RETRYABLE_STATUSES = frozenset({408, 429, 500, 502, 503, 504})
    RETRYABLE_EXCEPTIONS = (
        http.client.RemoteDisconnected,
        http.client.ResponseNotReady,
        ConnectionResetError,
        ConnectionRefusedError,
        socket.timeout,
        socket.gaierror,
    )

    @dataclass(frozen=True)
    class Response:
        status: int
        body: bytes
        headers: http.client.HTTPMessage

    def parse_retry_after(header_value: str | None) -> int | None: ...

    def backoff_seconds(attempt: int, retry_after: int | None = None) -> float: ...

    def request_with_retries(
        method: str,
        url: str,
        *,
        host: str,
        headers: dict[str, str],
        body: str | None = None,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        max_retries: int = DEFAULT_MAX_RETRIES,
        sleep: Callable[[float], None] = time.sleep,
    ) -> Response: ...
    ```
  - **Behavior:**
    - The helper returns a small `Response(status, body, headers)`
      dataclass. The body is **read into memory inside the helper**
      before the connection is closed, and the `HTTPMessage` headers
      are exposed directly (case-insensitive lookup via
      `response.headers.get("Link", "")`). This is the only design
      that lets callers see the body, the status, and the `Link`
      header after the connection is closed in a `finally` per
      attempt. (Earlier draft proposed returning the raw
      `HTTPResponse` without reading the body; that is impossible —
      `read()` requires an open connection — and is rejected.)
    - Opens `http.client.HTTPSConnection(host, timeout=timeout)`.
      Internally translates `timeout=0` to `None` (the stdlib's
      "block forever" sentinel) before constructing the connection,
      so `--timeout 0` matches its documented meaning. `0` and
      negative values that the CLI did not pre-validate are
      rejected here as a defense-in-depth check.
    - Calls `conn.request(method, url, body=body, headers=headers)`,
      then `conn.getresponse()`. Reads the body via `resp.read()`
      and captures `resp.headers` (the `HTTPMessage`) inside the
      `try` block, then closes the connection in `finally`.
      Returns the captured `Response`. The `Link` header is read by
      callers as `response.headers.get("Link", "")`, preserving
      `get_all_pages` semantics without exposing the live socket.
    - On `RETRYABLE_EXCEPTIONS` or status in `RETRYABLE_STATUSES`,
      sleeps `backoff_seconds(attempt, retry_after=...)` and retries
      while `attempt < max_retries`. After exhausting retries, raises
      the last transport error or `RuntimeError("API error {status}: {body[:200]}")`
      to match the existing message shape. The connection is closed
      in a `finally` per attempt.
    - Honors `Retry-After` via `parse_retry_after` (returns `None`
      when missing or unparseable). When `Retry-After` is present
      and ≥ 0, the helper sleeps exactly that long, **capped at
      `DEFAULT_MAX_BACKOFF_SECONDS` (30s)** to avoid hanging on a
      hostile or misconfigured `Retry-After: 3600` header. When
      absent, the helper sleeps `backoff_seconds(attempt)` =
      `2 ** attempt` seconds, capped at 30s. (The cap is the same
      value as the default timeout — the review noted that an
      uncapped `Retry-After` could stall a run for an hour.)
    - `sleep` is injectable so tests can assert without sleeping.
  - **Tests:** `tests/test_http_retry.py` (new). Use the
    `FakeSleeper` from `tests/_fakes.py` (Pre-Implementation P5) to
    avoid real sleeps.
    - `test_retries_on_5xx_then_succeeds` — 5xx twice then 200;
      `FakeSleeper.calls` is `[1, 2]` (or any monotonically
      increasing sequence).
    - `test_respects_retry_after_header` — server returns 503 +
      `Retry-After: 7`, helper sleeps exactly 7 before retrying.
    - `test_does_not_retry_on_404` — single call, `FakeSleeper.calls`
      is `[]`.
    - `test_does_not_retry_on_401_403` — single call each.
    - `test_retries_on_remote_disconnected` — first attempt raises
      `http.client.RemoteDisconnected`, second succeeds.
    - `test_exhausts_retries_then_raises_runtime_error` — 5xx
      `max_retries + 1` times, last error is a `RuntimeError` with
      the standard message.
    - `test_timeout_zero_translates_to_blocking` — `timeout=0` is
      internally translated to `None` (the stdlib "no timeout"
      sentinel) before constructing `HTTPSConnection`, so callers
      see the documented "block forever" behavior. A separate
      `test_negative_timeout_raises` covers the defense-in-depth
      rejection.
    - `test_max_retries_zero_means_no_retry` — 5xx once, raises
      `RuntimeError` after exactly one attempt.
    - `test_parse_retry_after_handles_missing_unparseable_and_valid` —
      unit tests for the small utility.

- [ ] **Wire the helper into `GitHubAPI`.**
  - **File:** `src/github_usage/api.py`
  - **Changes:**
    - `GitHubAPI.__init__` accepts optional `timeout` and `max_retries`
      keyword arguments with the new defaults. Store on `self`.
    - Replace the body of `GitHubAPI.request` (the existing
      `http.client.HTTPSConnection` / `conn.request` / `conn.getresponse`
      / `try-finally conn.close` block) with a call to
      `http_retry.request_with_retries(...)`. Read
      `response.status`, `response.body.decode("utf-8")`, and
      `response.headers.get("Link", "")` off the returned
      `Response` dataclass (case-insensitive header lookup,
      identical to the prior `resp.getheader("Link", "")`).
    - **`self._last_link` is removed.** The `_last_link` attribute
      existed only to ferry the `Link` header from `request()` to
      `get_all_pages()`. With the helper returning the full
      `Response`, `get_all_pages()` reads
      `response.headers.get("Link", "")` directly from each page's
      result. **Existing test assertions on `api._last_link`
      (`tests/test_api.py:106, 109`) must be updated to set the
      `Link` header on the mock response's `headers` mapping
      instead.** (See P8.)
    - **Delete the 403 / `Retry-After` branch entirely** (per
      Pre-Implementation P1). 403 now raises
      `RuntimeError("API error 403: {data[:200]}")` like any other
      non-retryable status. The `_retries` parameter and the
      recursive call site are removed.
    - Keep the 404 billing-endpoint message; keep the JSON-decode
      error; keep the "message in dict" handling in
      `get_all_pages`. None of that changes.
  - **Tests:** extend `tests/test_api.py` (existing) with
    - `test_request_uses_configured_timeout` — patch
      `github_usage.http_retry.http.client.HTTPSConnection`,
      assert it's constructed with `timeout=12` when
      `GitHubAPI(..., timeout=12)`.
    - `test_request_retries_on_5xx` — 5xx twice then 200, assert
      `FakeSleeper.calls` is `[1, 2]`.
    - `test_max_retries_zero_means_no_retry` — 5xx once, raises.
    - `test_403_no_longer_retries` — replacement for the old
      `test_request_retries_on_403_with_retry_after`. 403 +
      `Retry-After: 7` raises `RuntimeError` after a single attempt
      with no sleep. Update the existing test name and assertion
      rather than adding a new one.
    - `test_404_billing_message_still_works` — preserved behavior.
  - **Done when:** `python -m unittest tests.test_api tests.test_http_retry`
    passes; `bash scripts/check` passes; `bash scripts/smoke` passes.

- [ ] **Wire the helper into `send_email`.**
  - **File:** `src/github_usage/email_report.py`
  - **Changes:**
    - `send_email` accepts `timeout` and `max_retries` keyword
      arguments with the new defaults. It builds the JSON body, then
      calls `http_retry.request_with_retries(..., host="api.resend.com", ...)`
      and uses `response.status` / `response.body.decode("utf-8", errors="replace")`
      off the returned `Response` dataclass.
    - After the call, if `response.status not in (200, 201)`, raise
      the same `RuntimeError(f"Resend API error {response.status}: {body[:300]}")`
      as today.
  - **Tests:** extend `tests/test_email_report.py` (existing).
    - `test_send_email_uses_configured_timeout`.
    - `test_send_email_retries_on_5xx`.
    - `test_send_email_raises_runtime_error_after_exhausted_retries`.

### Phase 2: Surface the flags to the CLI

- [ ] **Add `--timeout` and `--max-retries` to the email-report parser.**
  - **File:** `src/github_usage/cli_parsers.py` (extracted in
    Pre-Implementation P7) — function `_email_parser`; or
    `src/github_usage/cli.py` if P7 was not done.
  - **Changes:**
    - Add `--timeout` with `type=float`, `default=http_retry.DEFAULT_TIMEOUT_SECONDS`.
    - Add `--max-retries` with `type=int`, `default=http_retry.DEFAULT_MAX_RETRIES`.
    - Reject `--max-retries < 0` and `--timeout < 0` after `parse_args`
      in `_run_email_report` (consistent with the existing
      `--max-repos < 1` check on `cli.py:189`).
  - **Plumbing:** in `_run_email_report`, construct
    `GitHubAPI(token, timeout=args.timeout, max_retries=args.max_retries)`
    and pass `timeout=...` and `max_retries=...` to
    `email_report.send_email(...)` (the legacy `cli.py:270` call).
    After fetching `user = api.request("GET", "/user")` (line 233),
    pass that dict into `check_user_scope(api, user=user)` (per P3)
    so the email-report flow does not issue a second `/user` request.
  - **Tests:** extend the existing email-report CLI test file with
    - `test_default_timeout_is_30` — no flag → API constructed with
      `timeout=30`.
    - `test_custom_timeout_is_passed_through` — `--timeout 5` →
      `timeout=5`.
    - `test_default_max_retries_is_3`.
    - `test_custom_max_retries_is_passed_through`.
    - `test_negative_max_retries_is_rejected` — exit code 1, error
      message mentions `--max-retries`.
    - `test_negative_timeout_is_rejected`.
  - **Done when:** `bash scripts/smoke` still passes (it now
    exercises `github-usage email-report --help` per P6).

- [ ] **Add `--timeout` and `--max-retries` to the legacy parser.**
  - **File:** `src/github_usage/cli_parsers.py` (or `cli.py`),
    function `_legacy_parser`.
  - **Changes:** mirror the email-report additions. After
    `parse_args`, validate the same way and reject negative values.
  - **Plumbing:** in `_run_legacy_report`, pass
    `timeout=args.timeout, max_retries=args.max_retries` to
    `legacy_main(...)` as keyword arguments. (Per Pre-Implementation
    P2, `legacy_main` already accepts these.) No env vars are
    involved; the values travel through the call stack.
  - **Tests:** extend `tests/test_cli.py` with
    - `test_default_timeout_is_30` for legacy.
    - `test_custom_timeout_is_passed_to_legacy_main` — `--timeout 5`
      causes `legacy_main(..., timeout=5)` to be called (assert via
      `mock.patch` on `legacy_report.main`).
    - `test_negative_timeout_is_rejected` for legacy.

### Phase 3: Docs and hygiene

- [ ] **Update `README.md`.**
  - Mention `--timeout` and `--max-retries` in the flag table / option
    list for both subcommands.
  - Add a "Timeout and retry" subsection under "Scheduled Email
    Reports" explaining the 30s / 3-retry defaults, the worst-case
    `4 × 30 + 7 ≈ 127s` wall time, and that `--timeout 0` is
    translated to "block forever" (the stdlib "no timeout" sentinel;
    this is a one-line clarification, not a stdlib quirk).
  - No env-var documentation is needed (per Pre-Implementation P2,
    the env-var channel was removed).

- [ ] **Update the manual `HELP` string in `src/github_usage/cli.py`.**
  - `cli.py:16-57` defines the `HELP` constant that the legacy
    parser prints for `-h`/`--help` (the parser uses
    `add_help=False` at line 83, so `argparse` does not generate
    a help string of its own). New flags added only to
    `argparse` would be invisible in `github-usage --help`.
  - Add the following lines under "Legacy report options:":
    - `  --timeout SECONDS       HTTP timeout per attempt (default 30)`
    - `  --max-retries N         Retries on 408/429/5xx/transport errors (default 3)`
  - And the same two lines under "Email-report options:" so the
    email-report flow documents the flags too.
  - Document the `--timeout 0` → "block forever" behavior inline
    in both entries.

- [ ] **Update `.github-usage/config.example.toml`.**
  - Add commented-out `timeout = 30.0` and `max_retries = 3` keys
    under the `[email_report]` section with a one-line comment
    explaining the defaults.

- [ ] **Update `src/github_usage/setup_config.py`.**
  - Add `"timeout": 30.0` and `"max_retries": 3` to
    `DEFAULT_EMAIL_REPORT` (line 20) so existing user configs that
    don't set these keys still get the documented defaults. The
    values must match `http_retry.DEFAULT_TIMEOUT_SECONDS` and
    `http_retry.DEFAULT_MAX_RETRIES`; use the constants rather
    than hard-coding the literals so a future change to the
    defaults stays in sync.
  - Extend `email_report_args(config)` (line 167) to emit
    `--timeout` and `--max-retries` from the merged config so
    `scripts/send-email-report.sh` actually forwards them. Emit
    these args even when they equal the defaults (CI / launchd
    users run with a fixed config and benefit from explicit
    values for debugging). Skip emission only when the value is
    `None` (i.e. the user explicitly cleared the key).
  - Extend `write_config(path, config)` (line 132) so the
    generated `config.toml` round-trips the new keys — otherwise
    a user that runs `setup` after this change will silently
    drop them.
  - Add a test in `tests/test_setup_config.py` (existing or
    new) asserting that `email_report_args(load_config(...))`
    includes both `--timeout 30.0` and `--max-retries 3` for the
    default config, and that a config that overrides
    `timeout = 5` produces `--timeout 5`.

- [ ] **Update `src/github_usage/setup_wizard.py` (if it generates
  CLI args / config).**
  - If the wizard writes the `email-report` arg list or the
    `.env.email-report` file, add a brief prompt or docstring note
    that `--timeout` and `--max-retries` are now available. The
    default behavior must remain unchanged. (Most of the actual
    plumbing is in `setup_config.py` above; this task is just
    the user-facing prompt / docstring touch-up.)

- [ ] **Update `.github/workflows/email-report.yml`.**
  - Add `--timeout 30 --max-retries 3` to the `github-usage
    email-report` invocation (or omit, since these are the
    defaults — but make the choice explicit and add a comment).

- [ ] **Update `CHANGELOG.md`.**
  - Add entries under "Unreleased" → "Added" and "Changed":
    - Added: `--timeout` and `--max-retries` flags on `github-usage`
      and `github-usage email-report`. Default 30s timeout, 3
      retries with exponential backoff for `api.github.com` and
      `api.resend.com` calls.
    - Changed: 403 responses from `api.github.com` are no longer
      retried automatically; users see a `RuntimeError` immediately
      (per Pre-Implementation P1).

- [ ] **Run the full verification chain.**
  - `bash scripts/check`
  - `bash scripts/smoke`
  - `bash scripts/docs-check`
  - `python -m unittest discover -s tests`
  - All must pass before the plan is marked done.

- [ ] **Update `TO_DO.md`.**
  - Tick the line-22 checkbox `- [x]`.
  - Prepend a `**Done:** 2026-06-19` note (one line) describing what
    was added and any deviation from this plan.

- [ ] **Archive the plan.**
  - Move this file to `docs/superpowers/plans/archived/` per
    `AGENTS.md` Done Criteria.

---

## Risks & Open Questions

1. **`Link` header preservation in the helper's return type.**
   `get_all_pages` reads `resp.getheader("Link", "")` directly off the
   `http.client.HTTPResponse`. The helper now returns a `Response`
   dataclass whose `headers` field is the raw `http.client.HTTPMessage`
   (case-insensitive `.get("Link", "")`). `get_all_pages` reads it
   from each `Response`; the legacy `self._last_link` attribute is
   removed. **Resolved.**
2. **`timeout=0` semantics.** The stdlib treats `timeout=0` as
   non-blocking (`BlockingIOError` on `connect()`), not as
   "block forever." The helper internally translates `timeout=0`
   to `None` (the stdlib's "no timeout" sentinel) before
   constructing `HTTPSConnection`, so the CLI's `--timeout 0`
   matches its documented meaning. **Resolved.**
3. **Uncapped `Retry-After` headers.** A server that returns
   `Retry-After: 3600` would otherwise stall a run for an hour.
   The helper caps the honored `Retry-After` value at
   `DEFAULT_MAX_BACKOFF_SECONDS` (30s). **Resolved.**
4. **Backoff vs. rate-limit interaction.** If a user passes
   `--max-retries 10` on a quota-bounded run, we will hammer the API
   past the limit. The `Retry-After` path fires first, so the
   practical risk is bounded; the plan accepts this and does not add
   a per-tenant cap.
5. **Removed 403 / `Retry-After` retry.** The original code retried
   403 responses with a `Retry-After` header, which is what
   `check_user_scope`'s 200-only check used to flow around. After
   P1 the 403 branch is gone, and 403 raises immediately. **Impact
   assessment:** `check_user_scope` is a 200-only test, so 403s
   there are failures (not retried before, and not retried after).
   The only consumer-facing 403+`Retry-After` path was in
   `api.py:52-57`, which is exercised from `cli.py:233` (`/user`)
   and indirectly from `legacy_report.py`. None of these callers
   depended on the 403 retry to succeed; they all consume the
   resulting data. **Resolution:** delete the branch; document the
   behavior change in CHANGELOG.
6. **Backoff thundering herd.** Back-to-back retries with the same
   `attempt` count across processes can thunder-herd GitHub on a
   multi-worker CI run. Out of scope; jitter is a future plan.

---

## Acceptance Criteria

- `GitHubAPI(..., timeout=30, max_retries=3)` is the new default.
- `send_email(..., timeout=30, max_retries=3)` is the new default.
- `request_with_retries` returns a `Response(status, body, headers)`
  dataclass; the body is read into memory and the connection is
  closed before the helper returns. Callers use
  `response.headers.get("Link", "")` for `Link` parsing.
- 408 / 429 / 5xx responses retry with exponential backoff and
  honor `Retry-After`. Honored `Retry-After` is capped at
  `DEFAULT_MAX_BACKOFF_SECONDS` (30s).
- Transport errors (timeouts, connection resets, DNS) retry up to
  `max_retries` times.
- 403 responses raise `RuntimeError` immediately (per P1; the
  legacy 403+`Retry-After` branch is removed).
- `auth.check_user_scope(api)` uses `api.request("GET", "/user")`
  and inherits the new timeout/retry behavior (per P3). Callers
  do not call `/user` twice (per P8 and the duplicate-`/user`
  resolution in the design).
- `legacy_report.main` accepts `timeout` and `max_retries` keyword
  args and threads them through to `GitHubAPI` (per P2).
- `--timeout` and `--max-retries` work on both subcommands and are
  validated at parse time; `--timeout 0` is translated internally
  to `None` so the stdlib "no timeout" semantics apply.
- `setup_config.DEFAULT_EMAIL_REPORT` and `email_report_args`
  emit `--timeout` and `--max-retries` so `scripts/send-email-report.sh`
  forwards them.
- The manual `HELP` string in `cli.py` lists both new flags under
  the appropriate sections.
- The README's "Timeout and retry" subsection documents the
  worst-case wall time of `4 × 30 + 7 ≈ 127s`.
- No live API calls in tests (per `AGENTS.md`).
- `cli.py` stays under 400 lines (per P7).
- `scripts/check`, `scripts/smoke`, `scripts/docs-check`, and
  `unittest discover` all pass.
- `TO_DO.md` line 22 is checked off; this plan is archived.
