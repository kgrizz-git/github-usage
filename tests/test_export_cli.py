import contextlib
import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

FIXTURES = Path(__file__).parent / "fixtures"


def _report_data():
    return json.loads((FIXTURES / "export_report_data.json").read_text())


class LegacyExportCliTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        import shutil

        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_export_csv_writes_file(self):
        from github_usage import cli

        data = _report_data()
        with (
            mock.patch.dict(os.environ, {"GITHUB_TOKEN": "fake-token"}, clear=True),
            mock.patch("github_usage.cli.resolve_token", return_value="fake-token"),
            mock.patch("github_usage.cli.check_user_scope", return_value=True),
            mock.patch("github_usage.cli.legacy_main", return_value="octocat"),
            mock.patch("github_usage.cli.report_data.build_report_data", return_value=data),
        ):
            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                code = cli.main(
                    [
                        "--export",
                        "csv",
                        "--no-interactive",
                        "--output",
                        os.path.join(self.tmpdir, "out.csv"),
                    ]
                )

        self.assertEqual(code, 0)
        self.assertTrue(os.path.exists(os.path.join(self.tmpdir, "out.csv")))

    def test_json_prints_to_stdout_without_output(self):
        from github_usage import cli

        data = _report_data()
        with (
            mock.patch.dict(os.environ, {"GITHUB_TOKEN": "fake-token"}, clear=True),
            mock.patch("github_usage.cli.resolve_token", return_value="fake-token"),
            mock.patch("github_usage.cli.check_user_scope", return_value=True),
            mock.patch("github_usage.cli.legacy_main", return_value="octocat"),
            mock.patch("github_usage.cli.report_data.build_report_data", return_value=data),
        ):
            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                code = cli.main(["--json", "--no-interactive"])

        self.assertEqual(code, 0)
        # JSON should appear in stdout
        body = stdout.getvalue()
        # The export and the "Exported to:" line both print; the JSON object is present
        self.assertIn('"username"', body)

    def test_json_with_output_writes_to_file(self):
        from github_usage import cli

        data = _report_data()
        path = os.path.join(self.tmpdir, "out.json")
        with (
            mock.patch.dict(os.environ, {"GITHUB_TOKEN": "fake-token"}, clear=True),
            mock.patch("github_usage.cli.resolve_token", return_value="fake-token"),
            mock.patch("github_usage.cli.check_user_scope", return_value=True),
            mock.patch("github_usage.cli.legacy_main", return_value="octocat"),
            mock.patch("github_usage.cli.report_data.build_report_data", return_value=data),
        ):
            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                code = cli.main(["--json", "--no-interactive", "--output", path])

        self.assertEqual(code, 0)
        self.assertTrue(os.path.exists(path))
        with open(path, encoding="utf-8") as f:
            result = json.loads(f.read())
        self.assertEqual(result["username"], "[redacted-user]")

    def test_output_without_export_errors(self):
        from github_usage import cli

        with mock.patch.dict(os.environ, {"GITHUB_TOKEN": "fake-token"}, clear=True):
            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                code = cli.main(
                    ["--no-interactive", "--output", os.path.join(self.tmpdir, "out.json")]
                )

        self.assertEqual(code, 1)
        self.assertIn("--output requires", stdout.getvalue())

    def test_json_and_export_mutually_exclusive(self):
        from github_usage import cli

        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            code = cli.main(["--json", "--export", "csv", "--no-interactive"])

        self.assertEqual(code, 1)
        self.assertIn("mutually exclusive", stdout.getvalue())

    def test_month_flag_removed(self):
        from github_usage import cli

        # --month is not registered in the legacy parser.
        stdout = io.StringIO()
        stderr = io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            code = cli.main(["--month", "2026-05", "--no-interactive"])

        self.assertNotEqual(code, 0)

    def test_export_none_skips_writing(self):
        from github_usage import cli

        with (
            mock.patch.dict(os.environ, {"GITHUB_TOKEN": "fake-token"}, clear=True),
            mock.patch("github_usage.cli.resolve_token", return_value="fake-token"),
            mock.patch("github_usage.cli.legacy_main", return_value="octocat"),
        ):
            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                code = cli.main(["--export", "none", "--no-interactive"])

        self.assertEqual(code, 0)
        # No "Exported to:" line
        self.assertNotIn("Exported to:", stdout.getvalue())

    def test_token_positional_before_flags(self):
        from github_usage import cli

        seen_argv: list[list[str]] = []

        def capture_token(*, argv=None):
            seen_argv.append(list(argv) if argv is not None else None)
            return "ghp_fake"

        with (
            mock.patch("github_usage.cli.resolve_token", side_effect=capture_token),
            mock.patch("github_usage.cli.legacy_main", return_value="octocat") as legacy_main,
        ):
            code = cli.main(["ghp_fake", "--no-interactive"])

        self.assertEqual(code, 0)
        legacy_main.assert_called_once()
        self.assertTrue(seen_argv)
        # Fix #1: the pre-check now passes only the peeled token so resolve_token
        # reads "ghp_fake" as the token, not the "github-usage" program name.
        self.assertEqual(seen_argv[0], ["ghp_fake"])

    def test_token_positional_only(self):
        from github_usage import cli

        with (
            mock.patch("github_usage.cli.resolve_token", return_value="ghp_fake"),
            mock.patch("github_usage.cli.legacy_main", return_value="octocat") as legacy_main,
        ):
            code = cli.main(["ghp_fake"])

        self.assertEqual(code, 0)
        legacy_main.assert_called_once()


class EmailReportExportCliTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        import shutil

        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_email_report_dry_run_with_export(self):
        from github_usage import cli

        data = _report_data()
        with (
            mock.patch.dict(os.environ, {"GITHUB_TOKEN": "fake-token"}, clear=True),
            mock.patch("github_usage.cli.resolve_token", return_value="fake-token"),
            mock.patch("github_usage.cli.GitHubAPI") as api_cls,
            mock.patch("github_usage.cli.check_user_scope", return_value=True),
            mock.patch("github_usage.cli.report_data.build_report_data", return_value=data),
        ):
            api = api_cls.return_value
            api.request.return_value = {"login": "octocat"}
            path = os.path.join(self.tmpdir, "out.txt")
            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                code = cli.main(
                    [
                        "email-report",
                        "--dry-run",
                        "--skip-actions",
                        "--export",
                        "text",
                        "--output",
                        path,
                    ]
                )

        self.assertEqual(code, 0)
        self.assertTrue(os.path.exists(path))
        with open(path, encoding="utf-8") as f:
            content = f.read()
        # Text redaction redacts dollar amounts (and emails); usernames in text
        # are NOT redacted by design (too many false positives on ordinary words).
        self.assertIn("[redacted-amount]", content)
        # Dry-run prints the unredacted body to stdout.
        self.assertIn("octocat", stdout.getvalue())

    def test_email_report_output_without_export_errors(self):
        from github_usage import cli

        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            code = cli.main(
                [
                    "email-report",
                    "--dry-run",
                    "--output",
                    os.path.join(self.tmpdir, "out.txt"),
                ]
            )

        self.assertEqual(code, 1)
        self.assertIn("--output requires", stdout.getvalue())

    def test_email_report_export_csv(self):
        from github_usage import cli

        data = _report_data()
        path = os.path.join(self.tmpdir, "out.csv")
        with (
            mock.patch.dict(os.environ, {"GITHUB_TOKEN": "fake-token"}, clear=True),
            mock.patch("github_usage.cli.resolve_token", return_value="fake-token"),
            mock.patch("github_usage.cli.GitHubAPI") as api_cls,
            mock.patch("github_usage.cli.check_user_scope", return_value=True),
            mock.patch("github_usage.cli.report_data.build_report_data", return_value=data),
        ):
            api = api_cls.return_value
            api.request.return_value = {"login": "octocat"}
            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                code = cli.main(
                    [
                        "email-report",
                        "--dry-run",
                        "--skip-actions",
                        "--export",
                        "csv",
                        "--output",
                        path,
                    ]
                )

        self.assertEqual(code, 0)
        self.assertTrue(os.path.exists(path))
        with open(path, encoding="utf-8") as f:
            content = f.read()
        self.assertIn("### Report Metadata ###", content)
        self.assertIn("[redacted-user]", content)

    def test_email_report_export_csv_auto_filename(self):
        from github_usage import cli

        data = _report_data()
        with (
            mock.patch.dict(os.environ, {"GITHUB_TOKEN": "fake-token"}, clear=True),
            mock.patch("github_usage.cli.resolve_token", return_value="fake-token"),
            mock.patch("github_usage.cli.GitHubAPI") as api_cls,
            mock.patch("github_usage.cli.check_user_scope", return_value=True),
            mock.patch("github_usage.cli.report_data.build_report_data", return_value=data),
            mock.patch(
                "github_usage.cli.export_report.generate_filename",
                return_value=os.path.join(self.tmpdir, "auto.csv"),
            ),
        ):
            api = api_cls.return_value
            api.request.return_value = {"login": "octocat"}
            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                code = cli.main(
                    [
                        "email-report",
                        "--dry-run",
                        "--skip-actions",
                        "--export",
                        "csv",
                    ]
                )

        self.assertEqual(code, 0)
        self.assertTrue(os.path.exists(os.path.join(self.tmpdir, "auto.csv")))
        self.assertIn("Exported to:", stdout.getvalue())

    def test_email_report_html_format_success(self):
        from github_usage import cli

        data = _report_data()
        with (
            mock.patch.dict(os.environ, {"GITHUB_TOKEN": "fake-token"}, clear=True),
            mock.patch("github_usage.cli.resolve_token", return_value="fake-token"),
            mock.patch("github_usage.cli.GitHubAPI") as api_cls,
            mock.patch("github_usage.cli.check_user_scope", return_value=True),
            mock.patch("github_usage.cli.report_data.build_report_data", return_value=data),
        ):
            api = api_cls.return_value
            api.request.return_value = {"login": "octocat"}
            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                code = cli.main(
                    [
                        "email-report",
                        "--dry-run",
                        "--email-format",
                        "html",
                    ]
                )

        self.assertEqual(code, 0)
        output = stdout.getvalue()
        self.assertIn("<!DOCTYPE html>", output)
        self.assertNotIn("not yet supported", output)

    def test_email_report_default_format_sends_text_only(self):
        from github_usage import cli

        data = _report_data()
        with (
            mock.patch.dict(
                os.environ,
                {
                    "GITHUB_TOKEN": "fake-token",
                    "RESEND_API_KEY": "re_key",
                    "REPORT_EMAIL": "user@example.com",
                    "RESEND_FROM": "reports@example.com",
                },
                clear=True,
            ),
            mock.patch("github_usage.cli.resolve_token", return_value="fake-token"),
            mock.patch("github_usage.cli.GitHubAPI") as api_cls,
            mock.patch("github_usage.cli.check_user_scope", return_value=True),
            mock.patch("github_usage.cli.report_data.build_report_data", return_value=data),
            mock.patch("github_usage.cli.email_report.send_email") as mock_send,
        ):
            api = api_cls.return_value
            api.request.return_value = {"login": "octocat"}
            code = cli.main(["email-report"])

        self.assertEqual(code, 0)
        mock_send.assert_called_once()
        self.assertIsNone(mock_send.call_args.kwargs["html"])


if __name__ == "__main__":
    unittest.main()
