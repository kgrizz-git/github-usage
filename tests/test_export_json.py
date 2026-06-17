import datetime
import io
import json
import unittest

from github_usage import export_json
from tests.conftest import load_export_report_data


class ExportJsonTests(unittest.TestCase):
    def setUp(self):
        self.data = load_export_report_data()

    def _roundtrip(self):
        buf = io.StringIO()
        export_json.write(self.data, buf)
        return json.loads(buf.getvalue())

    def test_serializes_report_data(self):
        result = self._roundtrip()
        self.assertEqual(result["username"], "octocat")
        self.assertEqual(result["period"], "current_month")
        self.assertEqual(result["actions"]["minutes"], 1250.0)
        self.assertEqual(len(result["repo_consumers"]["by_minutes"]), 2)

    def test_preserves_api_estimate(self):
        result = self._roundtrip()
        self.assertEqual(result["api_estimate"]["core_limit"], 5000)
        self.assertEqual(result["api_estimate"]["core_remaining"], 4900)

    def test_pretty_printed(self):
        buf = io.StringIO()
        export_json.write(self.data, buf)
        self.assertIn("\n  ", buf.getvalue())

    def test_handles_datetime(self):
        self.data["generated_at"] = datetime.datetime(2026, 6, 15, 14, 30, 0)
        result = self._roundtrip()
        self.assertEqual(result["generated_at"], "2026-06-15T14:30:00")

    def test_handles_date(self):
        self.data["period"] = datetime.date(2026, 6, 1)
        result = self._roundtrip()
        self.assertEqual(result["period"], "2026-06-01")

    def test_unicode_preserved(self):
        self.data["warnings"] = ["Über cost: $5.00"]
        result = self._roundtrip()
        self.assertEqual(result["warnings"][0], "Über cost: $5.00")

    def test_trailing_newline(self):
        buf = io.StringIO()
        export_json.write(self.data, buf)
        self.assertTrue(buf.getvalue().endswith("\n"))

    def test_writes_to_stdout(self):
        import sys

        captured = io.StringIO()
        real_stdout = sys.stdout
        sys.stdout = captured
        try:
            export_json.write(self.data, sys.stdout)
        finally:
            sys.stdout = real_stdout
        result = json.loads(captured.getvalue())
        self.assertEqual(result["username"], "octocat")


if __name__ == "__main__":
    unittest.main()
