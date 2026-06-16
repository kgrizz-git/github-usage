import unittest
from contextlib import redirect_stdout
from io import StringIO
from unittest import mock


class AccountReportTests(unittest.TestCase):
    def test_show_account_info_prints_user_login(self):
        from github_usage.report_account import show_account_info

        api = mock.Mock()
        api.request.return_value = {"login": "octocat", "type": "User", "plan": {"name": "free"}}

        stdout = StringIO()
        with redirect_stdout(stdout):
            username, user_type = show_account_info(api)

        self.assertEqual(username, "octocat")
        self.assertEqual(user_type, "User")
        self.assertIn("Username:   octocat", stdout.getvalue())
        self.assertIn("Account:    User", stdout.getvalue())
