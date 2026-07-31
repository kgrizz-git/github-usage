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

    def test_detail_rows_include_forecast(self) -> None:
        from datetime import date

        data = {
            "account": {"type": "User", "plan": {"name": "free"}},
            "monthly_costs": {
                "actions": {"net": 1.0},
                "copilot": {"net": 0.0},
                "git_lfs": {"net": 0.0},
                "total": {"net": 1.0},
            },
            "actions": {
                "minutes": 1000.0,
                "minutes_limit": 2000,
                "minutes_percent": 50.0,
                "storage_gb_hours": 3.0,
                "storage_avg_mb": 250.0,
                "storage_limit_mb": 500,
                "storage_percent": 50.0,
            },
            "copilot": {"total_requests": 100.0},
            "repo_actions": [],
            "storage_analysis": {"repos": []},
            "errors": {},
        }
        rows = legacy_report_detail_rows(
            data,
            "octocat",
            premium_requests_limit=1000.0,
            reference_date=date(2026, 7, 15),
        )
        metrics = [metric for metric, _value in rows]
        self.assertIn("── Forecast ──", metrics)
        projected_values = [value for metric, value in rows if "Projected" in metric]
        self.assertTrue(any("2066.7 / 2000" in value for value in projected_values))
        self.assertTrue(any("516.7 MB / 500 MB" in value for value in projected_values))
        self.assertTrue(any("206.7 / 1000" in value for value in projected_values))

    def test_detail_rows_omit_forecast_before_day_3(self) -> None:
        from datetime import date

        data = {
            "account": {},
            "monthly_costs": {
                "actions": {"net": 0.0},
                "copilot": {"net": 0.0},
                "git_lfs": {"net": 0.0},
                "total": {"net": 0.0},
            },
            "actions": {
                "minutes": 100.0,
                "minutes_limit": 2000,
                "storage_avg_mb": 50.0,
                "storage_limit_mb": 500,
            },
            "copilot": {"total_requests": 10.0},
            "repo_actions": [],
            "storage_analysis": {"repos": []},
            "errors": {},
        }
        from github_usage.report_forecast_data import build_report_forecast

        self.assertIsNone(build_report_forecast(data, reference_date=date(2026, 7, 2)))
        rows = legacy_report_detail_rows(
            data,
            "octocat",
            premium_requests_limit=1000.0,
            reference_date=date(2026, 7, 2),
        )
        metrics = [metric for metric, _value in rows]
        self.assertNotIn("── Forecast ──", metrics)

    def test_summary_rows_private_first_when_split_present(self) -> None:
        data = {
            "monthly_costs": {
                "total": {"gross": 10.0, "discount": 2.0, "net": 8.0},
                "actions": {"net": 5.0},
                "copilot": {"net": 2.0},
                "git_lfs": {"net": 1.0},
            },
            "actions": {
                "minutes": 1250.0,
                "minutes_limit": 2000,
                "minutes_percent": 62.5,
                "private_minutes": 900.0,
                "private_minutes_percent": 45.0,
                "public_minutes": 350.0,
                "storage_gb_hours": 12.5,
                "storage_avg_mb": 42.0,
                "storage_limit_mb": 500,
                "storage_percent": 8.4,
                "private_storage_avg_mb": 30.0,
                "public_storage_avg_mb": 12.0,
                "private_storage_gb_hours": 8.0,
                "public_storage_gb_hours": 4.5,
            },
            "storage_analysis": {"repos": []},
            "errors": {},
        }
        rows = legacy_report_summary_rows(data, "octocat")
        minutes = next(value for metric, value in rows if metric == "Actions minutes")
        self.assertIn("Private 900.0 / 2,000 min (45.0%)", minutes)
        self.assertIn("public 350.0 min (free)", minutes)
        storage = next(value for metric, value in rows if metric == "Actions storage (avg MB)")
        self.assertIn("Private 30.0 / 500 MB", storage)
        self.assertIn("public 12.0 MB (free)", storage)

    def test_detail_rows_include_public_minutes_and_expiry(self) -> None:
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
                "private_minutes": 40.0,
                "private_minutes_percent": 2.0,
                "public_minutes": 60.0,
                "storage_gb_hours": 3.0,
                "storage_avg_mb": 10.0,
                "storage_limit_mb": 500,
                "storage_percent": 2.0,
                "private_storage_avg_mb": 8.0,
                "public_storage_avg_mb": 2.0,
                "private_storage_gb_hours": 2.0,
                "public_storage_gb_hours": 1.0,
            },
            "repo_actions": [],
            "repo_consumers": {},
            "storage_analysis": {
                "repos": [
                    {
                        "name": "octocat/heavy",
                        "visibility": "private",
                        "total_storage": 0.5,
                        "artifact_storage_gb": 0.5,
                        "release_storage_gb": 0.0,
                        "artifact_count": 12,
                        "expiring_soon_count": 3,
                        "expired_count": 1,
                    }
                ],
            },
            "errors": {},
        }
        rows = legacy_report_detail_rows(data, "octocat")
        by_metric = {metric: value for metric, value in rows}
        self.assertEqual(by_metric["Public Actions minutes"], "60.0 (free)")
        self.assertTrue(
            any(
                "12 artifacts" in value and "3 expire ≤7d" in value and "1 expired" in value
                for _metric, value in rows
            )
        )


if __name__ == "__main__":
    unittest.main()
