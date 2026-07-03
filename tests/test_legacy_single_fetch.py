"""Integration tests: legacy export uses a single data fetch."""

from __future__ import annotations

import contextlib
import io
import os
import unittest
from unittest import mock

from tests.test_export_cli import _report_data


class LegacySingleFetchTests(unittest.TestCase):
    def test_export_uses_session_data_without_second_fetch(self) -> None:
        from github_usage import cli

        sample = _report_data()

        def _session(**_kwargs):
            return 0, sample, "octocat"

        with (
            mock.patch.dict(
                os.environ,
                {"GITHUB_TOKEN": "fake-token", "GITHUB_USAGE_CLI": "1"},
                clear=True,
            ),
            mock.patch("github_usage.cli.resolve_token", return_value="fake-token"),
            mock.patch(
                "github_usage.legacy_report.run_legacy_report_session", side_effect=_session
            ),
            mock.patch("github_usage.legacy_report_data.build_legacy_report_data") as build,
        ):
            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                code = cli.main(["--json", "--no-interactive"])

        self.assertEqual(code, 0)
        build.assert_not_called()
        self.assertIn("octocat", stdout.getvalue())
