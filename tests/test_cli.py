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

    def test_setup_help_exits_zero(self):
        from github_usage import cli

        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            code = cli.main(["setup", "--help"])

        self.assertEqual(code, 0)
        self.assertIn("github-usage setup", stdout.getvalue())

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

    def test_email_report_invalid_token_message_omits_user_scope_remediation(self):
        from github_usage import cli

        with (
            mock.patch.dict(os.environ, {"GITHUB_TOKEN": "fake-token"}, clear=True),
            mock.patch("github_usage.cli.GitHubAPI") as api_cls,
            mock.patch("github_usage.cli.check_user_scope", return_value=False),
        ):
            api = api_cls.return_value
            api.request.return_value = {"login": "octocat"}
            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                code = cli.main(["email-report", "--dry-run", "--skip-actions"])

        self.assertEqual(code, 1)
        output = stdout.getvalue()
        self.assertIn("not valid for this operation", output)
        self.assertNotIn("'user' scope", output)
        self.assertNotIn("gh auth refresh", output)

    def test_email_report_does_not_mutate_sys_argv(self):
        from github_usage import cli

        sentinel_argv = ["sentinel-program", "sentinel-arg"]
        with (
            mock.patch.object(cli.sys, "argv", list(sentinel_argv)),
            mock.patch("github_usage.cli.resolve_token", return_value=None),
        ):
            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                cli.main(["email-report", "--help"])
            self.assertEqual(cli.sys.argv, sentinel_argv)

    def test_email_report_bad_flag_returns_nonzero_without_raising(self):
        from github_usage import cli

        with (
            mock.patch.dict(os.environ, {}, clear=True),
            mock.patch("github_usage.cli.resolve_token", return_value="fake-token"),
        ):
            stdout = io.StringIO()
            stderr = io.StringIO()
            with (
                contextlib.redirect_stdout(stdout),
                contextlib.redirect_stderr(stderr),
            ):
                code = cli.main(["email-report", "--max-repos", "foo"])

        self.assertNotEqual(code, 0)
        self.assertIn("--max-repos", stderr.getvalue())

    def test_main_catches_systemexit_from_subcommand(self):
        from github_usage import cli

        with mock.patch("github_usage.cli._run_email_report", side_effect=SystemExit(7)):
            code = cli.main(["email-report"])

        self.assertEqual(code, 7)

    def test_main_catches_systemexit_from_setup(self):
        from github_usage import cli

        with mock.patch("github_usage.setup_wizard.run_setup", side_effect=SystemExit(2)):
            code = cli.main(["setup"])

        self.assertEqual(code, 2)

    def test_token_positional_with_version(self):
        from github_usage import cli

        with mock.patch("github_usage.cli.resolve_token") as resolve_token:
            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                code = cli.main(["ghp_fake_token", "--version"])

        self.assertEqual(code, 0)
        self.assertIn("github-usage", stdout.getvalue())
        resolve_token.assert_not_called()


if __name__ == "__main__":
    unittest.main()
