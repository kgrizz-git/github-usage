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
