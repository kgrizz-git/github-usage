import unittest
from contextlib import redirect_stdout
from io import StringIO
from unittest import mock


class ActionsReportTests(unittest.TestCase):
    def test_show_actions_os_breakdown_aggregates_correctly(self):
        from github_usage.report_actions import show_actions_os_breakdown

        api = mock.Mock()
        repos = [{"owner": {"login": "octocat"}, "name": "api"}]

        with mock.patch("github_usage.report_actions.get_actions_from_runs") as get_runs:
            get_runs.return_value = (10.0, {"UBUNTU": 600000, "WINDOWS": 0, "MACOS": 0}, {})

            stdout = StringIO()
            with redirect_stdout(stdout):
                show_actions_os_breakdown(api, repos)

            output = stdout.getvalue()
            self.assertIn("octocat/api", output)
            self.assertIn("UBUNTU", output)
            self.assertIn("10.0 min", output)
            self.assertIn("TOTAL:", output)

    def test_show_actions_per_repo_skips_malformed_repos(self):
        from github_usage.report_actions import show_actions_per_repo

        api = mock.Mock()
        repos = [
            {},
            {"name": "missing-owner"},
            {"owner": {}},
            {"owner": None, "name": "x"},
            {"owner": {"login": "octocat"}, "name": "valid"},
        ]

        with mock.patch(
            "github_usage.report_actions.get_actions_per_repo",
            return_value=(0.0, 0.0, {}),
        ):
            stdout = StringIO()
            with redirect_stdout(stdout):
                repo_data = show_actions_per_repo(api, repos)

        self.assertEqual(len(repo_data), 1)
        self.assertEqual(repo_data[0][0], "octocat/valid")
        # Only the valid repo's row should appear in the output.
        self.assertIn("octocat/valid", stdout.getvalue())
        self.assertNotIn("x", stdout.getvalue().splitlines()[-1])

    def test_render_actions_summary_visibility_and_larger_marker(self):
        from github_usage.report_actions import render_actions_summary

        actions = {
            "minutes": 3000.0,
            "storage_gb_hours": 100.0,
            "private_minutes": 1000.0,
            "public_minutes": 2000.0,
            "unattributed_minutes": 0.0,
            "private_minutes_percent": 50.0,
            "private_storage_gb_hours": 60.0,
            "public_storage_gb_hours": 40.0,
            "unattributed_storage_gb_hours": 0.0,
            "internal_repo_count": 0,
            "filtered": False,
            "sku_breakdown": {
                "actions_linux": {
                    "unitType": "minutes",
                    "grossQuantity": 1000,
                    "grossAmount": 0,
                    "discountAmount": 0,
                    "netAmount": 0,
                },
                "linux_4_core": {
                    "unitType": "minutes",
                    "grossQuantity": 10,
                    "grossAmount": 1,
                    "discountAmount": 0,
                    "netAmount": 1,
                },
            },
        }
        stdout = StringIO()
        with redirect_stdout(stdout):
            render_actions_summary(actions)
        out = stdout.getvalue()
        self.assertIn("Usage by Visibility", out)
        self.assertIn("Private (billable)", out)
        self.assertIn("Public (free)", out)
        self.assertIn("linux_4_core *", out)
        self.assertIn("larger runner", out)

    def test_render_limits_summary_uses_private_bucket(self):
        from datetime import date

        from github_usage.report_actions import render_limits_summary

        actions = {
            "minutes": 5000.0,
            "storage_gb_hours": 200.0,
            "private_minutes": 2181.3,
            "public_minutes": 4392.0,
            "unattributed_minutes": 0.0,
            "private_minutes_percent": 109.1,
            "private_storage_avg_mb": 227.5,
            "public_storage_avg_mb": 69.3,
            "private_storage_gb_hours": 165.3,
            "public_storage_gb_hours": 50.4,
            "filtered": False,
        }
        stdout = StringIO()
        with redirect_stdout(stdout):
            render_limits_summary(actions, reference_date=date(2026, 7, 15))
        out = stdout.getvalue()
        self.assertIn("private repos only", out)
        self.assertIn("2181.3", out)
        self.assertIn("4392.0", out)
        self.assertIn("free — no quota impact", out)
        self.assertIn("GB-hrs", out)
        self.assertIn("372", out)  # July allowance

    def test_show_actions_top_consumers_accepts_optional_visibility_by_repo(self):
        from github_usage.report_actions import show_actions_top_consumers

        repo_data = [
            ("octocat/private", 100.0, 0.0, 5.0, 1.0, {}),
            ("octocat/public", 50.0, 0.0, 2.0, 0.5, {}),
        ]
        stdout = StringIO()
        with redirect_stdout(stdout):
            show_actions_top_consumers(repo_data)
        self.assertIn("octocat/private", stdout.getvalue())
        self.assertNotIn("[private]", stdout.getvalue())

        stdout = StringIO()
        with redirect_stdout(stdout):
            show_actions_top_consumers(repo_data, visibility_by_repo={"octocat/private": "private"})
        out = stdout.getvalue()
        self.assertIn("octocat/private [private]", out)
        self.assertNotIn("octocat/public [", out)

    def test_render_limits_summary_suppresses_quota_when_only_public(self):
        from github_usage.report_actions import render_limits_summary

        actions = {
            "minutes": 100.0,
            "private_minutes": 0.0,
            "public_minutes": 100.0,
            "private_storage_avg_mb": 0.0,
            "public_storage_avg_mb": 10.0,
            "private_storage_gb_hours": 0.0,
            "public_storage_gb_hours": 5.0,
            "filtered": True,
        }
        stdout = StringIO()
        with redirect_stdout(stdout):
            render_limits_summary(actions)
        out = stdout.getvalue()
        self.assertIn("scanned repos", out)
        self.assertIn("quota math suppressed", out)
        self.assertNotIn("0.0 / 2000 min (0.0% used)", out)
