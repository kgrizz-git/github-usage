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

    def test_show_actions_os_breakdown_skips_malformed_repos(self):
        from github_usage.report_actions import show_actions_os_breakdown

        api = mock.Mock()
        repos = [
            {},
            {"name": "missing-owner"},
            {"owner": {}},
            {"owner": None, "name": "x"},
            {"owner": {"login": "octocat"}, "name": "valid"},
        ]

        with mock.patch(
            "github_usage.report_actions.get_actions_from_runs",
            return_value=(0.0, {"UBUNTU": 0, "WINDOWS": 0, "MACOS": 0}, {}),
        ):
            stdout = StringIO()
            with redirect_stdout(stdout):
                # Should not raise on any of the malformed shapes.
                show_actions_os_breakdown(api, repos)

        # With 0 minutes per repo, no per-repo "X min" lines print. The only
        # valid repo's name should not appear (because minutes=0 suppresses the
        # print), and the function should reach the "No detailed OS breakdown"
        # branch.
        self.assertIn("No detailed OS breakdown", stdout.getvalue())
