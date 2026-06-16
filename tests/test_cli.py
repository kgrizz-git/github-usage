import contextlib
import io
import os
import unittest
from unittest import mock


class CliTests(unittest.TestCase):
    def test_help_exits_zero_without_resolving_token(self):
        from github_usage import cli

        with mock.patch("github_usage.cli.resolve_token") as resolve_token:
            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                code = cli.main(["--help"])

        self.assertEqual(code, 0)
        self.assertIn("GitHub Monthly Usage Report", stdout.getvalue())
        resolve_token.assert_not_called()

    def test_missing_token_exits_one_with_clear_message(self):
        from github_usage import cli

        with mock.patch("github_usage.cli.resolve_token", return_value=None):
            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                code = cli.main([])

        self.assertEqual(code, 1)
        output = stdout.getvalue()
        self.assertIn("Error: No GitHub token found.", output)
        self.assertIn("Usage: github-usage <token>", output)
        self.assertIn("Or set GITHUB_TOKEN env var.", output)
        self.assertIn("Or run: gh auth login", output)

    def test_email_report_help_exits_zero_without_resolving_token(self):
        from github_usage import cli

        with mock.patch("github_usage.cli.resolve_token") as resolve_token:
            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                code = cli.main(["email-report", "--help"])

        self.assertEqual(code, 0)
        self.assertIn("github-usage email-report", stdout.getvalue())
        resolve_token.assert_not_called()

    def test_email_report_dry_run_requires_only_github_token(self):
        from github_usage import cli

        report_data = {
            "username": "octocat",
            "period": "current_month",
            "generated_at": "2026-06-15T14:30:00Z",
            "warnings": [],
            "errors": {},
            "actions": None,
            "copilot": None,
            "git_lfs": None,
            "monthly_costs": {"total": {"gross": 0.0, "discount": 0.0, "net": 0.0}},
            "repo_consumers": None,
            "artifact_storage": None,
            "release_assets": None,
            "api_estimate": {"notes": []},
            "insights": [],
        }

        stdout = io.StringIO()
        with (
            mock.patch.dict(os.environ, {"GITHUB_TOKEN": "fake-token"}, clear=True),
            mock.patch("github_usage.cli.GitHubAPI") as api_cls,
            mock.patch("github_usage.cli.check_user_scope", return_value=True),
            mock.patch("github_usage.report_data.build_report_data", return_value=report_data),
            contextlib.redirect_stdout(stdout),
        ):
            api = api_cls.return_value
            api.request.return_value = {"login": "octocat"}
            code = cli.main(["email-report", "--dry-run", "--skip-actions"])

        self.assertEqual(code, 0)
        self.assertIn("GitHub Usage Report for octocat", stdout.getvalue())

    def test_email_report_send_requires_resend_env(self):
        from github_usage import cli

        with mock.patch.dict(os.environ, {"GITHUB_TOKEN": "fake-token"}, clear=True):
            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                code = cli.main(["email-report"])

        self.assertEqual(code, 1)
        self.assertIn("RESEND_API_KEY", stdout.getvalue())
        self.assertIn("REPORT_EMAIL", stdout.getvalue())
        self.assertIn("RESEND_FROM", stdout.getvalue())

    def test_all_default_sections_skipped_is_invalid_without_artifact_storage(self):
        from github_usage import cli

        with mock.patch.dict(os.environ, {"GITHUB_TOKEN": "fake-token"}, clear=True):
            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                code = cli.main(
                    ["email-report", "--dry-run", "--skip-actions", "--skip-copilot", "--skip-lfs"]
                )

        self.assertEqual(code, 1)
        self.assertIn("all default report sections", stdout.getvalue())


if __name__ == "__main__":
    unittest.main()
