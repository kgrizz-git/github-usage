"""Tests for legacy terminal rendering from fixtures."""

from __future__ import annotations

import contextlib
import io
import json
import unittest
from pathlib import Path

from github_usage.legacy_terminal import render_legacy_report

FIXTURES = Path(__file__).parent / "fixtures"


class LegacyTerminalTests(unittest.TestCase):
    def test_render_includes_major_sections(self) -> None:
        export_fixture = json.loads((FIXTURES / "export_report_data.json").read_text())
        data = {
            **export_fixture,
            "account": {"login": "octocat", "type": "User", "plan": {}},
            "rate_limits": {"resources": {"core": {"limit": 5000, "remaining": 4000}}},
            "repo_actions": [
                {
                    "repo": "octocat/api",
                    "minutes": 900.0,
                    "storage_gb_hours": 10.0,
                    "avg_mb": 180.0,
                    "gross": 3.4,
                    "sku": {},
                }
            ],
            "actions_os_breakdown": {"repos": [], "totals": {}, "found": False},
            "billing_history": [],
            "storage_analysis": {"repos": []},
            "copilot_premium": None,
            "copilot_billing": None,
            "lfs_billing": None,
        }
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            render_legacy_report(data)
        output = buffer.getvalue()
        for heading in (
            "Account Info",
            "GitHub Actions Usage",
            "Per-Repository Actions Breakdown",
            "FINAL SUMMARY",
            "End of Report v3",
        ):
            self.assertIn(heading, output)

    def test_render_api_usage_section_with_measurement(self) -> None:
        from github_usage.legacy_terminal import render_api_usage

        estimate = {
            "actual_requests": 123,
            "total_requests": 130,
            "estimated_incremental_requests": 120,
            "core_limit": 5000,
            "core_remaining": 4877,
            "actual_requests_by_resource": {"billing": 120, "user": 1, "rate_limit": 1},
            "estimate_scope": "repo-sections-only",
            "from_cache": False,
        }
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            render_api_usage(estimate)
        output = buffer.getvalue()
        self.assertIn("REST API Usage", output)
        self.assertIn("123 (estimated 120)", output)
        self.assertIn("Core rate limit", output)
        self.assertIn(
            "docs.github.com/en/rest/using-the-rest-api/rate-limits-for-the-rest-api", output
        )

    def test_render_api_usage_silent_without_measurement(self) -> None:
        from github_usage.legacy_terminal import render_api_usage

        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            render_api_usage({})
            render_api_usage(None)
        self.assertEqual(buffer.getvalue(), "")

    def test_render_forecast_includes_projected_minutes(self) -> None:
        from datetime import date

        data = {
            "account": {"login": "octocat", "type": "User", "plan": {}},
            "rate_limits": {"resources": {"core": {"limit": 5000, "remaining": 4000}}},
            "actions": {
                "minutes": 1000.0,
                "minutes_limit": 2000,
                "minutes_percent": 50.0,
                "storage_avg_mb": 250.0,
                "storage_limit_mb": 500,
                "storage_percent": 50.0,
            },
            "copilot": {"total_requests": 100.0},
            "repo_actions": [],
            "actions_os_breakdown": {"repos": [], "totals": {}, "found": False},
            "billing_history": [],
            "storage_analysis": {"repos": []},
            "copilot_premium": None,
            "copilot_billing": None,
            "lfs_billing": None,
        }
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            render_legacy_report(
                data,
                include_forecast=True,
                premium_requests_limit=1000.0,
                reference_date=date(2026, 7, 15),
            )
        output = buffer.getvalue()
        self.assertIn("Monthly Forecast", output)
        self.assertIn("projected", output)
        self.assertIn("run-out", output)

    def test_render_forecast_disabled(self) -> None:
        from datetime import date

        data = {
            "account": {"login": "octocat", "type": "User", "plan": {}},
            "rate_limits": {"resources": {"core": {"limit": 5000, "remaining": 4000}}},
            "actions": {"minutes": 1000.0, "storage_avg_mb": 250.0},
            "repo_actions": [],
            "actions_os_breakdown": {"repos": [], "totals": {}, "found": False},
            "billing_history": [],
            "storage_analysis": {"repos": []},
        }
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            render_legacy_report(
                data,
                include_forecast=False,
                premium_requests_limit=1000.0,
                reference_date=date(2026, 7, 15),
            )
        output = buffer.getvalue()
        self.assertNotIn("Monthly Forecast", output)

    def test_cached_legacy_report_renders_forecast_from_profile(self) -> None:
        from datetime import date
        from unittest import mock

        from github_usage.legacy_report import run_legacy_report_session
        from github_usage.report_cache import CacheHit

        data = {
            "username": "octocat",
            "account": {"login": "octocat", "type": "User", "plan": {}},
            "rate_limits": {"resources": {"core": {"limit": 5000, "remaining": 4000}}},
            "actions": {"minutes": 1000.0, "storage_avg_mb": 250.0},
            "copilot": {"total_requests": 100.0},
            "repo_actions": [],
            "actions_os_breakdown": {"repos": [], "totals": {}, "found": False},
            "billing_history": [],
            "storage_analysis": {"repos": []},
            "copilot_premium": None,
            "copilot_billing": None,
            "lfs_billing": None,
        }
        with (
            mock.patch("github_usage.legacy_report.resolve_token", return_value="fake-token"),
            mock.patch(
                "github_usage.legacy_report.load_cached_report",
                return_value=(data, "octocat", CacheHit(from_cache=True)),
            ),
            mock.patch("github_usage.report_cache.resolve_cache_max_age", return_value=3600),
            mock.patch("github_usage.report_forecast_data.date") as mock_date,
        ):
            mock_date.today.return_value = date(2026, 7, 15)
            buffer = io.StringIO()
            with contextlib.redirect_stdout(buffer):
                code, _data, _username, _cache = run_legacy_report_session()
        self.assertEqual(code, 0)
        output = buffer.getvalue()
        self.assertIn("Monthly Forecast", output)
        self.assertIn("projected", output)


class LegacySessionBaselineTests(unittest.TestCase):
    def test_fresh_session_baseline_covers_pre_builder_calls(self) -> None:
        from unittest import mock

        from github_usage import legacy_report
        from github_usage.report_api_usage import SCOPE_FULL_REPORT
        from tests._fakes import CountingFakeAPI

        api = CountingFakeAPI(
            request_responses={
                ("GET", "/user", ()): {"login": "octocat", "type": "User", "plan": {}},
                ("GET", "/rate_limit", ()): {
                    "resources": {"core": {"limit": 5000, "remaining": 5000}}
                },
            },
            pages_responses={"/user/repos": []},
        )
        with (
            mock.patch("github_usage.legacy_report.GitHubAPI", return_value=api),
            mock.patch("github_usage.legacy_report.resolve_token", return_value="fake-token"),
            mock.patch("github_usage.legacy_report.print_header"),
            mock.patch("github_usage.legacy_report.render_legacy_report"),
        ):
            code, data, username, _cache = legacy_report.run_legacy_report_session(max_repos=10)
        self.assertEqual(code, 0)
        self.assertEqual(username, "octocat")
        assert data is not None
        estimate = data["api_estimate"]
        self.assertEqual(estimate["estimate_scope"], SCOPE_FULL_REPORT)
        # Pre-builder /user + /rate_limit calls (scope check + fetch each)
        # fall inside the measured window.
        self.assertGreaterEqual(estimate["actual_requests_by_resource"].get("user", 0), 2)
        self.assertGreaterEqual(estimate["actual_requests_by_resource"].get("rate_limit", 0), 2)

    def test_cached_session_marks_from_cache_without_new_calls(self) -> None:
        from unittest import mock

        from github_usage import legacy_report
        from github_usage.report_cache import CacheHit

        cached = {
            "username": "octocat",
            "api_estimate": {"actual_requests": 5, "total_requests": 9},
        }
        with (
            mock.patch("github_usage.legacy_report.resolve_token", return_value="fake-token"),
            mock.patch(
                "github_usage.legacy_report.load_cached_report",
                return_value=(cached, "octocat", CacheHit(from_cache=True)),
            ),
            mock.patch("github_usage.legacy_report.print_header"),
            mock.patch("github_usage.legacy_report.render_legacy_report"),
        ):
            code, data, username, _cache = legacy_report.run_legacy_report_session()
        self.assertEqual(code, 0)
        assert data is not None
        self.assertTrue(data["api_estimate"]["from_cache"])
        self.assertEqual(data["api_estimate"]["actual_requests"], 5)
