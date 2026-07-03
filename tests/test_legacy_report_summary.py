"""Tests for legacy report TUI summary helpers."""

from __future__ import annotations

import unittest

from github_usage.legacy_report_summary import (
    legacy_report_detail_rows,
    legacy_report_summary_rows,
)


class LegacyReportSummaryTests(unittest.TestCase):
    def test_summary_rows_include_billed_and_scanned_storage(self) -> None:
        data = {
            "monthly_costs": {
                "total": {"gross": 10.0, "discount": 2.0, "net": 8.0},
                "actions": {"net": 5.0},
                "copilot": {"net": 2.0},
                "git_lfs": {"net": 1.0},
            },
            "actions": {
                "minutes": 123.4,
                "minutes_limit": 2000,
                "minutes_percent": 6.2,
                "storage_gb_hours": 12.5,
                "storage_avg_mb": 42.0,
                "storage_limit_mb": 500,
                "storage_percent": 8.4,
            },
            "storage_analysis": {
                "repos": [
                    {"name": "octocat/a", "total_storage": 1.25},
                ],
            },
            "errors": {},
        }
        rows = legacy_report_summary_rows(data, "octocat")
        self.assertEqual(rows[2][1], "123.4 / 2000 min (6.2%)")
        self.assertIn("42.0", rows[3][1])
        self.assertEqual(rows[4], ("Artifacts/releases (scan)", "1.25 GB"))

    def test_detail_rows_include_repo_storage_sections(self) -> None:
        data = {
            "account": {"type": "User", "plan": {"name": "free"}},
            "monthly_costs": {
                "actions": {"net": 1.0},
                "copilot": {"net": 0.0},
                "git_lfs": {"net": 0.0},
                "total": {"net": 1.0},
            },
            "actions": {
                "minutes": 100.0,
                "minutes_limit": 2000,
                "minutes_percent": 5.0,
                "storage_gb_hours": 3.0,
                "storage_avg_mb": 10.0,
                "storage_limit_mb": 500,
                "storage_percent": 2.0,
            },
            "repo_actions": [
                {
                    "repo": "octocat/big",
                    "minutes": 50.0,
                    "storage_gb_hours": 2.0,
                    "avg_mb": 8.0,
                    "gross": 0.5,
                },
                {"repo": "octocat/small", "minutes": 1.0, "storage_gb_hours": 0.0, "avg_mb": 0.0},
            ],
            "repo_consumers": {
                "by_minutes": [{"repo": "octocat/big", "minutes": 50.0, "gross": 0.5}],
                "by_cost": [{"repo": "octocat/big", "minutes": 50.0, "gross": 0.5}],
            },
            "storage_analysis": {
                "repos": [
                    {"name": "octocat/releases", "total_storage": 0.5},
                ],
            },
            "artifact_storage": {
                "top_repos": [{"repo": "octocat/releases", "artifact_bytes": 1024**3}],
            },
            "insights": ["octocat/big accounts for 50% of Actions minutes."],
            "warnings": [],
            "errors": {},
        }
        rows = legacy_report_detail_rows(data, "octocat")
        metrics = [metric for metric, _value in rows]
        self.assertIn("── Per-repo Actions storage (billed) ──", metrics)
        self.assertIn("── Artifact & release storage (API scan) ──", metrics)
        self.assertTrue(any(value.startswith("8.0 MB avg") for _metric, value in rows))
        self.assertTrue(
            any(_metric == "octocat/releases" and "0.50 GB" in value for _metric, value in rows)
        )
        self.assertIn("── Insights ──", metrics)

    def test_detail_rows_explain_empty_artifact_scan(self) -> None:
        data = {
            "account": {},
            "monthly_costs": {"actions": {}, "copilot": {}, "git_lfs": {}, "total": {"net": 0.0}},
            "actions": {
                "minutes": 0.0,
                "minutes_limit": 2000,
                "minutes_percent": 0.0,
                "storage_gb_hours": 0.0,
                "storage_avg_mb": 0.0,
                "storage_limit_mb": 500,
                "storage_percent": 0.0,
            },
            "storage_analysis": {"repos": []},
            "errors": {},
        }
        rows = legacy_report_detail_rows(data, "user")
        note_rows = [value for metric, value in rows if metric == "Note"]
        self.assertTrue(any("No artifacts or release assets" in value for value in note_rows))
