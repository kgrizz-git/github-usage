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
