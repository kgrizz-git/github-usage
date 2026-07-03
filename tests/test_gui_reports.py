"""Tests for gui_backend reporting helpers."""

from __future__ import annotations

import unittest
from unittest import mock

from github_usage.gui_backend import export_legacy_report, run_legacy_report_data


class LegacyReportBackendTests(unittest.TestCase):
    """Legacy report data assembly without launching the TUI."""

    def test_run_legacy_report_no_token(self) -> None:
        with mock.patch("github_usage.gui_backend.resolve_token", return_value=None):
            code, data, err, cache = run_legacy_report_data()
        self.assertEqual(code, 1)
        self.assertIsNone(data)
        self.assertFalse(cache.from_cache)

    def test_export_requires_data(self) -> None:
        sample = {"account": {"total_spend": 0}, "actions": {}, "storage": {}}
        with mock.patch(
            "github_usage.gui_backend.export_report.export",
            return_value="/tmp/out.csv",
        ):
            code, message = export_legacy_report(sample, "user", "csv", "/tmp/out.csv")
        self.assertEqual(code, 0)
        self.assertIn("Exported", message)


if __name__ == "__main__":
    unittest.main()
