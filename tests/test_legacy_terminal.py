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
