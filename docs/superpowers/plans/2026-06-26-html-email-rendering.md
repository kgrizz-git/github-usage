# Plan: HTML email rendering for `--email-format html`

> **Status:** IN PROGRESS
>
> **Date:** 2026-06-26

## Objective

Unblock the `--email-format html` option by adding an HTML rendering path to the email report system. The `--email-format` flag already accepts `"html"` as a choice; the CLI currently rejects it with `"html is not yet supported."` This plan implements a full HTML email body renderer and wires it through the email dispatch flow.

## Motivation

The `--email-format text|html` flag was added to `cli_parsers.py` with HTML rendering deferred. The plain-text formatter in `email_report.format_report_email()` is stable. Users want rich HTML emails for better readability in email clients.

## Current State

- `cli_parsers.py:52` — `--email-format` accepts `("text", "html")` with default `"text"`.
- `cli.py:153-155` — `_validate_email_flags()` blocks `html` with an error message.
- `cli.py:42` — HELP string says `html deferred`.
- `email_report.py` — Contains `format_report_email()` (plain-text) and `send_email()` (Resend, sends `text` field only).
- Resend API supports both `text` and `html` fields on the email payload.

## Proposed Implementation

### 1. Add `format_html_report()` to `email_report.py`

Create a new function `format_html_report(data: dict) -> str` that renders the same report data as an HTML document. The HTML should be self-contained (inline styles, no external CSS) and responsive.

> **Size budget:** `email_report.py` is currently 248 lines. The nine `_format_html_*_section()` functions plus the wrapper and tuple will add roughly 120-160 lines, keeping the file well under the 500-line soft limit. If a section formatter exceeds ~30 lines, factor a small inner helper rather than letting one function balloon. `cli.py` grows by only a handful of lines and stays under 400.

Each `_format_*_section()` function in `email_report.py` should get a corresponding `_format_html_*_section()` that returns a list of HTML string fragments. A new `_SECTION_HTML_FORMATTERS` tuple drives the generation — its element order **must match** `_SECTION_FORMATTERS`.

> **Structure note:** Mirroring `format_report_email()`, the `format_html_report()` wrapper handles three things directly (outside `_SECTION_HTML_FORMATTERS`):
> 1. The report header (username, generated date, period)
> 2. Warnings (styled as a highlighted alert box)
> 3. REST API Quota Notes (footnote-style)
>
> The per-section formatters in `_SECTION_HTML_FORMATTERS` handle only the individual data sections.

> **Period text:** The data dict carries `period: "current_month"` (with an underscore; see `report_data.py:255`). The plain-text formatter hardcodes the literal string `"Period: current month"` (with a space) — `format_html_report()` must match this literal to stay consistent with the plain-text body, not surface the raw `current_month` value.

The HTML structure mirrors the plain-text sections:

```html
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>GitHub Usage Report</title>
  <style>
    /* inline-friendly: minimal, self-contained */
    body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif; margin: 0; padding: 20px; color: #24292f; }
    h1 { font-size: 20px; border-bottom: 1px solid #d0d7de; padding-bottom: 8px; }
    h2 { font-size: 16px; margin-top: 20px; }
    table { border-collapse: collapse; width: 100%; margin: 8px 0; }
    th, td { text-align: left; padding: 6px 10px; border: 1px solid #d0d7de; }
    th { background: #f6f8fa; }
    ul { padding-left: 20px; }
    .warning { background: #fff8c5; border: 1px solid #d4a72c; padding: 8px; border-radius: 4px; }
    .meta { color: #656d76; font-size: 14px; }
  </style>
</head>
<body>
  ...
</body>
</html>
```

> **Email-client CSS note:** Some email clients (Gmail mobile app, Outlook on Windows) strip `<style>` blocks in `<head>`. For production, use inline `style` attributes on elements (e.g., `<td style="padding: 6px 10px; border: 1px solid #d0d7de;">`) or run the output through a CSS-inliner like `premailer`. For this first pass, the `<style>` block in `<head>` is acceptable for most modern clients.

> **HTML escaping — required:** All user-supplied and untrusted data interpolated into the HTML output must be escaped using `html.escape()` from Python's standard library (default `quote=True`, which escapes `<`, `>`, `&`, `"`, and `'`). This includes:
> - `username` (header)
> - `repo` names (consumers, artifact storage, release assets)
> - `insight` strings (key insights)
> - `warning` strings
> - `model` names (copilot by-model breakdown)
> - `section` / `message` strings (unavailable data errors)
> - `note` strings (REST API quota notes)
>
> Without escaping, a repo name like `org/foo&bar` would produce invalid HTML. Add `import html` to `email_report.py` for `html.escape()`.

Reusable helpers:
- `_cost_line()` (line 33) — plain-text cost string. The HTML path needs a corresponding `_html_cost_line()` helper that returns a table row string fragment (called by `_format_html_monthly_costs_section()`).
- `_bytes_to_mb()` (line 29) — remains usable as-is; the HTML formatter wraps its return value in a `<td>`.
- `fmt_price()` (from `report_helpers`) — formats numeric floats, output is inherently safe to insert into HTML without additional escaping; should be reused as-is.
- `_generated_line()` (line 17) — used directly by `format_report_email()` (the wrapper), not inside a section formatter. Its HTML equivalent is inlined directly inside `format_html_report()` (wrapping the output in a `<span class="meta">` element), not extracted into a separate helper.

Key sections to render:
- Header (username, generated date, period) — handled directly by `format_html_report()`
- Warnings (styled as a highlighted alert box) — handled directly by `format_html_report()`
- Actions (table with minutes, storage, cost)
- Copilot (list with by-model breakdown)
- Git LFS (cost line)
- Monthly Costs (table with gross/discount/net per category)
- Repo Consumers (tables for by-minutes and by-cost)
- Artifact Storage (list of repos with MB)
- Release Assets (list of repos with MB)
- Key Insights (bullet list)
- Unavailable Data (list of errors)
- REST API Quota Notes (footnote-style) — handled directly by `format_html_report()`

### 2. Wire HTML through `send_email()`

Update `send_email()` to accept an optional `html: str | None` parameter. When `html` is provided, the Resend payload includes both `text` and `html` fields. The Resend API renders the HTML version in clients that support it while preserving plain-text fallback.

```python
def send_email(
    api_key: str,
    from_addr: str,
    to_addr: str,
    subject: str,
    body: str,
    html: str | None = None,
    timeout: float | None = None,
    max_retries: int | None = None,
) -> None:
    ...
    payload = {
        "from": from_addr,
        "to": [to_addr],
        "subject": subject,
        "text": body,
    }
    if html:
        payload["html"] = html
    ...
```

### 3. Update `_run_email_report()` in `cli.py`

In the `_run_email_report()` function, after generating the plain-text body, define `html_body` unconditionally to avoid scoping issues (`NameError`) in the dry-run and send paths:

```python
        body = email_report.format_report_email(data)
        html_body = email_report.format_html_report(data) if args.email_format == "html" else None
```

Update the `email_report.send_email()` call in the dispatch flow to include `html=html_body` (cli.py lines 243-251):

```python
        email_report.send_email(
            os.environ["RESEND_API_KEY"],
            os.environ["RESEND_FROM"],
            os.environ["REPORT_EMAIL"],
            subject,
            body,
            html=html_body,
            timeout=args.timeout,
            max_retries=args.max_retries,
        )
```

> **Export interaction (no change needed):** The export path (lines 227-236) uses `body` (plain-text) for `--export text` and `data` for other formats. This behavior is correct regardless of `--email-format` — the `html_body` variable is only for email delivery, never for export. Do not change the export path.

> **Dry-run path:** The current `print(body, end="")` on line 238 prints the plain-text body. When `args.email_format == "html"`, this must print the HTML body instead. Since `html_body` is unconditionally defined, the dry-run block works without `NameError`:

```python
        if args.dry_run:
            print(html_body if args.email_format == "html" else body, end="")
            return 0
```

The change in `_validate_email_flags()` should remove the HTML blocking logic.

### 4. Update module docstring and CLI text

Update the module docstring in `email_report.py:1` from:
```
"""Plain-text email report formatting and Resend delivery."""
```
to:
```
"""Email report formatting (plain-text and HTML) and Resend delivery."""
```

Update the email-report parser description in `cli_parsers.py:38` from:
```python
description="Send or preview a scheduled plain-text GitHub usage email report.",
```
to:
```python
description="Send or preview a scheduled GitHub usage email report.",
```

Update the HELP string in `cli.py:42` from:
```
--email-format FMT      Email body format: text | html (html deferred)
```
to:
```
--email-format FMT      Email body format: text | html
```

### 5. Tests

#### A. Unit Tests in `tests/test_email_report.py`

HTML rendering:
- `test_format_html_report_renders_html_sections` — verify HTML output contains expected sections
- `test_format_html_report_contains_valid_html_structure` — verify `<!DOCTYPE html>`, `<html>`, `<body>`, `<style>` tags
- `test_format_html_report_renders_minimal_data` — passes a minimal data dict (matching `test_format_report_email_renders_today_when_generated_at_missing`) and verifies no exceptions and valid HTML structure
- `test_format_html_report_escapes_special_chars` — inject `<`, `>`, `&`, `"` into repo names, warnings, and insights; assert they appear as `&lt;`, `&gt;`, `&amp;`, `&quot;` in the output (validates that the default `html.escape()` `quote=True` is in effect, not just the three-char `<`/`>`/`&` form)
- `test_format_html_report_well_formed_html` — parses the HTML output using `html.parser.HTMLParser` to programmatically verify that all opened tags are correctly closed and there are no parsing errors

HTML formatter ordering:
- `test_section_html_formatters_order_matches_text_formatters` — verifies that `_SECTION_HTML_FORMATTERS` and `_SECTION_FORMATTERS` have the same length and that each HTML formatter name maps to its text counterpart (e.g., `_format_actions_section` ↔ `_format_html_actions_section`)

send_email payload:
- `test_send_email_posts_html_payload_when_provided` — verify that the Resend payload contains both `text` (the original body) and `html` (the provided HTML) fields, the `to`/`from`/`subject` fields are unchanged, and `conn.close()` is still called once
- `test_send_email_posts_text_only_when_html_none` — backward compatibility: no `html` field when `html=None`, payload matches the pre-change shape exactly

#### B. CLI and Integration Tests in `tests/test_export_cli.py`

CLI dry-run and integration:
- Update `test_email_report_html_format_errors` to `test_email_report_html_format_success` — verifies that running `email-report` with `--email-format html` succeeds (returns code 0 and prints HTML) under a dry-run. Requires mock infrastructure:
  - Mock `os.environ` to include a fake GITHUB_TOKEN
  - Mock `github_usage.cli.GitHubAPI` and its return value for `/user`
  - Mock `check_user_scope` to return `True`
  - Mock `report_data.build_report_data` to return a valid dummy report dictionary
  - Assert that stdout contains the generated HTML (`<!DOCTYPE html>`) and the exit code is `0`
- `test_email_report_default_format_sends_text_only` — regression test to verify that running `email-report` without `--email-format html` (defaulting to text) sends a text-only payload. This must exercise the real send path (no `--dry-run`), so the test must:
  - Set `RESEND_API_KEY`, `RESEND_FROM`, and `REPORT_EMAIL` in the mocked `os.environ` so `_missing_env` passes.
  - Mock `github_usage.cli.email_report.send_email` to a `mock.Mock()` that captures the call args.
  - Assert `send_email.call_args.kwargs["html"] is None`. The `html` kwarg is always present (the caller passes `html=html_body` unconditionally, per the `_run_email_report` change), so the assertion is on the value being `None`, not on the kwarg being absent.
  - The default format path also generates `html_body = None` (per the `_run_email_report` change), so this test is the regression guard for that wiring.

## Implementation Order

### Phase 1: HTML rendering function

- [ ] Add `format_html_report()` to `email_report.py` with all section renderers (and the new `import html` for `html.escape()`)
- [ ] Add tests for `format_html_report()`, including `HTMLParser` validation
- [ ] Add `test_section_html_formatters_order_matches_text_formatters`

### Phase 2: Wire through email dispatch

- [ ] Update `send_email()` to accept and send `html` parameter
- [ ] Update `_run_email_report()` to generate HTML and pass it to `send_email()`
- [ ] Update `_run_email_report()` dry-run path to print HTML body when format is `html`
- [ ] Update `_validate_email_flags()` to remove HTML blocking
- [ ] Update `test_email_report_html_format_errors` to `test_email_report_html_format_success` in `tests/test_export_cli.py`
- [ ] Add `test_email_report_default_format_sends_text_only` regression test to verify text-only payload by default
- [ ] Update CLI HELP string in `cli.py:42`
- [ ] Update parser description in `cli_parsers.py:38` (remove "plain-text")
- [ ] Update module docstring in `email_report.py:1`
- [ ] Add tests for `send_email()` HTML parameter
- [ ] Update `CHANGELOG.md`: change the existing `[Unreleased] → Added` entry from `--email-format text|html flag on email-report (HTML rendering deferred)` to reflect that the flag is now fully implemented (HTML renderer in `format_html_report`, both `text` and `html` sent through Resend).
- [ ] Extend `scripts/smoke` with a flag-presence check for `--email-format` (mirror the existing `--timeout` / `--max-retries` greps) so the help-string update is regression-protected.

### Phase 3: Verification

- [ ] Run `scripts/check`
- [ ] Run `scripts/smoke`
- [ ] Manual test — dry-run prints HTML: `python -m github_usage email-report --email-format html --dry-run`
- [ ] Manual test — dry-run prints plain-text (default): `python -m github_usage email-report --dry-run`
- [ ] Confirm that `scripts/check` exits cleanly and no test failures are introduced
- [ ] Run `scripts/docs-check` to verify that documentation checks pass after CLI HELP updates
- [ ] Remove the `Email Report Follow-Ups → "Add --email-format text|html HTML rendering"` line from `TO_DO.md` (per AGENTS.md; the changelog and archived plan are the historical record)

### Phase 4: Plan close-out

- [ ] Set the plan status banner to the canonical `> **Status:** COMPLETE` (colon outside the bold, as required by `scripts/docs-check`).
- [ ] Add a `**Done:**` note per phase with date, one-line summary, files touched, and tests added.
- [ ] Move the plan to `docs/superpowers/plans/archived/` so the active plans directory stays uncluttered.
- [ ] Note the merge commit at the top of the archived plan.

## Out of Scope

- Template file (e.g., a `.html` file on disk) — inline generation keeps dependencies minimal.
- CSS frameworks or external stylesheets — inline styles only for email client compatibility.
- HTML-to-text conversion — plain-text renderer already exists and is used as the fallback.
