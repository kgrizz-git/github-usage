"""API discovery for --month support.

Tests whether the GitHub billing endpoints accept ``since``/``until`` query
parameters for historical month queries. Per the repository's AGENTS.md,
live API calls must be gated behind an explicit environment variable.

Usage:
    GITHUB_USAGE_API_DISCOVERY=1 GITHUB_TOKEN=<token> \
        python3 -m github_usage.scripts.api_discovery_month

The script never prints the token. It writes a sanitized report to
``docs/api-discovery-month.md`` summarizing which endpoints filter by date
and which ignore the params. The report only contains endpoint URLs,
parameter names, and a yes/no for date support.
"""

from __future__ import annotations

import json
import os
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

REPORT_PATH = Path(__file__).resolve().parents[3] / "docs" / "api-discovery-month.md"


def _require_env(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        print(f"Error: {name} environment variable is required.", file=sys.stderr)
        sys.exit(2)
    return value


def _month_range(year: int, month: int) -> tuple[str, str]:
    """Return (since, until) ISO-8601 strings covering the given month."""
    since = datetime(year, month, 1, tzinfo=UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    if month == 12:
        next_month = datetime(year + 1, 1, 1, tzinfo=UTC)
    else:
        next_month = datetime(year, month + 1, 1, tzinfo=UTC)
    until = (next_month - timedelta(seconds=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
    return since, until


def _request(api, method: str, path: str, params: dict | None = None):
    """Make a request and return (status, body). Never logs auth headers."""
    try:
        data = api.request(method, path, params)
        return 200, data
    except RuntimeError as exc:
        return 0, str(exc)


def _summarize(data) -> str:
    if isinstance(data, dict):
        if "usageItems" in data and isinstance(data["usageItems"], list):
            return f"usageItems={len(data['usageItems'])}"
        return f"keys={list(data.keys())[:5]}"
    return type(data).__name__


def _print_endpoint_results(report_lines: list[str], findings: list[dict]) -> None:
    """Append the per-endpoint section to ``report_lines`` in place."""
    for finding in findings:
        same_shape = (
            finding["without_range"]["status"] == finding["with_range"]["status"]
            and finding["without_range"]["shape"] == finding["with_range"]["shape"]
        )
        verdict = "ignores date range" if same_shape else "responds differently (likely filtered)"
        report_lines.extend(
            [
                f"### {finding['label']}",
                "",
                f"- Path: `{finding['path']}`",
                f"- Base params: `{finding['params']}`",
                f"- Without date range: status={finding['without_range']['status']}, "
                f"shape={finding['without_range']['shape']}",
                f"- With date range: status={finding['with_range']['status']}, "
                f"shape={finding['with_range']['shape']}",
                f"- Verdict: **{verdict}**",
                "",
            ]
        )


def _print_summary(report_lines: list[str], findings: list[dict]) -> str:
    """Append the summary section to ``report_lines`` in place.

    Returns the summary text so the caller can also print it to stdout
    in the JSON dump.
    """
    all_same = all(
        f["without_range"]["status"] == f["with_range"]["status"]
        and f["without_range"]["shape"] == f["with_range"]["shape"]
        for f in findings
    )
    summary = (
        "All tested endpoints ignore the `since`/`until` parameters; --month must be **deferred** "
        "for historical queries. The flag remains accepted for label/filename purposes only."
        if all_same
        else "At least one endpoint appears to filter by date range; --month can be implemented "
        "for the endpoints that support it, with graceful fallback for those that do not."
    )
    report_lines.extend(["## Summary", "", summary, ""])
    return summary


def main() -> int:
    """Probe GitHub billing endpoints to discover month-filtering support."""
    _require_env("GITHUB_USAGE_API_DISCOVERY")
    token = _require_env("GITHUB_TOKEN")

    from github_usage.api import GitHubAPI  # local import to keep module cheap

    api = GitHubAPI(token)
    user_resp = api.request("GET", "/user")
    username = (user_resp or {}).get("login")
    if not username:
        print("Error: GitHub /user response did not include a login.", file=sys.stderr)
        return 1

    now = datetime.now(tz=UTC)
    prev_year = now.year if now.month > 1 else now.year - 1
    prev_month = now.month - 1 if now.month > 1 else 12
    since, until = _month_range(prev_year, prev_month)

    endpoints = [
        (
            "billing usage summary (Actions)",
            f"/users/{username}/settings/billing/usage/summary",
            {"product": "Actions"},
        ),
        (
            "billing usage summary (Copilot)",
            f"/users/{username}/settings/billing/usage/summary",
            {"product": "Copilot"},
        ),
        (
            "billing usage summary (git_lfs)",
            f"/users/{username}/settings/billing/usage/summary",
            {"product": "git_lfs"},
        ),
        (
            "premium request usage (copilot)",
            f"/users/{username}/settings/billing/premium_request/usage",
            {"product": "copilot"},
        ),
    ]

    findings: list[dict] = []
    for label, path, base_params in endpoints:
        without = _request(api, "GET", path, dict(base_params))
        with_range = _request(api, "GET", path, {**base_params, "since": since, "until": until})
        findings.append(
            {
                "label": label,
                "path": path,
                "params": sorted(base_params.keys()),
                "without_range": {
                    "status": without[0],
                    "shape": _summarize(without[1]),
                },
                "with_range": {
                    "status": with_range[0],
                    "shape": _summarize(with_range[1]),
                    "since": since,
                    "until": until,
                },
            }
        )

    report_lines = [
        "# API discovery: --month date-range support",
        "",
        f"Run at: {now.strftime('%Y-%m-%dT%H:%M:%SZ')}",
        f"Test month: {prev_year:04d}-{prev_month:02d}",
        f"Range tested: since={since}, until={until}",
        "",
        "## Per-endpoint results",
        "",
    ]
    _print_endpoint_results(report_lines, findings)
    summary = _print_summary(report_lines, findings)

    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text("\n".join(report_lines))
    print(f"Wrote {REPORT_PATH}")
    print()
    print(json.dumps({"summary": summary, "findings": findings}, indent=2, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
