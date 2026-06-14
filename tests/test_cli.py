import contextlib
import io
import unittest
from unittest import mock


class CliTests(unittest.TestCase):
    def test_help_exits_zero_without_resolving_token(self):
        from github_usage import cli

        with mock.patch("github_usage.legacy.resolve_token") as resolve_token:
            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                code = cli.main(["--help"])

        self.assertEqual(code, 0)
        self.assertIn("GitHub Monthly Usage Report", stdout.getvalue())
        resolve_token.assert_not_called()

    def test_missing_token_exits_one_with_clear_message(self):
        from github_usage import cli

        with mock.patch("github_usage.legacy.resolve_token", return_value=None):
            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                code = cli.main([])

        self.assertEqual(code, 1)
        self.assertIn("No GitHub token found", stdout.getvalue())
        self.assertIn("GITHUB_TOKEN", stdout.getvalue())


if __name__ == "__main__":
    unittest.main()
