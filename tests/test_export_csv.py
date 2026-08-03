import csv
import io
import unittest
from datetime import date
from unittest import mock

from github_usage import export_csv
from tests.conftest import load_export_report_data

# Forecast is omitted when day_of_month < 3; pin mid-month so section-presence
# assertions are calendar-independent (matches test_forecast_section_present).
_MID_MONTH = date(2026, 7, 15)

CSV_SECTIONS = [
    "Report Metadata",
    "Forecast",
    "Warnings",
    "Actions Usage",
    "Copilot Usage",
    "Git LFS",
    "Monthly Costs",
    "Top Repos by Minutes",
    "Top Repos by Cost",
    "Artifact Storage",
    "Release Assets",
    "Key Insights",
    "Unavailable Data",
    "Sources",
]


class ExportCsvTests(unittest.TestCase):
    def setUp(self):
        self.data = load_export_report_data()
        date_patcher = mock.patch("github_usage.report_forecast_data.date")
        mock_date = date_patcher.start()
        mock_date.today.return_value = _MID_MONTH
        self.addCleanup(date_patcher.stop)

    def _rows(self, data=None):
        buf = io.StringIO()
        export_csv.write(data if data is not None else self.data, buf)
        return list(csv.reader(io.StringIO(buf.getvalue().lstrip("\ufeff"))))

    def test_writes_sections(self):
        rows = self._rows()
        section_rows = [r[0] for r in rows if r and r[0].startswith("###")]
        for section in CSV_SECTIONS:
            self.assertIn(f"### {section} ###", section_rows)

    def test_writes_sku_breakdown(self):
        rows = self._rows()
        idx = rows.index(["### Actions Usage ###"])
        sub = []
        for row in rows[idx + 1 :]:
            if row and row[0].startswith("###"):
                break
            sub.append(row)
        self.assertIn(["sku_breakdown"], sub)
        header_idx = sub.index(["sku_breakdown"])
        self.assertEqual(
            sub[header_idx + 1],
            ["sku", "minutes", "storage_gb_hours", "gross", "discount", "net"],
        )
        data_rows = {r[0] for r in sub[header_idx + 2 :] if r}
        self.assertIn("actions_linux", data_rows)
        self.assertIn("actions_macos", data_rows)

    def test_writes_copilot_by_model(self):
        rows = self._rows()
        idx = rows.index(["### Copilot Usage ###"])
        sub = []
        for row in rows[idx + 1 :]:
            if row and row[0].startswith("###"):
                break
            sub.append(row)
        self.assertIn(["by_model"], sub)
        header_idx = sub.index(["by_model"])
        self.assertEqual(sub[header_idx + 1], ["model", "requests", "gross", "discount", "net"])
        model_names = {r[0] for r in sub[header_idx + 2 :] if r}
        self.assertIn("gpt-4.1", model_names)
        self.assertIn("claude-sonnet-4", model_names)

    def test_section_header_format(self):
        rows = self._rows()
        for row in rows:
            if row and row[0].startswith("###"):
                self.assertEqual(len(row), 1)
                self.assertTrue(row[0].startswith("### "))
                self.assertTrue(row[0].endswith(" ###"))

    def test_escapes_commas_and_quotes(self):
        self.data["warnings"] = ["Has, a comma", 'Has "quotes" inside']
        rows = self._rows()
        flat = [item for row in rows for item in row]
        self.assertIn("Has, a comma", flat)
        self.assertIn('Has "quotes" inside', flat)

    def test_writes_utf8_bom(self):
        buf = io.StringIO()
        export_csv.write(self.data, buf)
        self.assertTrue(buf.getvalue().startswith("\ufeff"))

    def test_none_values_become_empty(self):
        self.data["actions"] = {"minutes": None, "minutes_limit": 2000}
        rows = self._rows()
        actions_idx = rows.index(["### Actions Usage ###"])
        minutes_row = next(r for r in rows[actions_idx + 1 :] if r and r[0] == "minutes")
        self.assertEqual(minutes_row, ["minutes", ""])

    def test_none_section_coalesced_to_empty(self):
        self.data["copilot"] = None
        self.data["git_lfs"] = None
        self.data["repo_consumers"] = None
        self.data["artifact_storage"] = None
        self.data["release_assets"] = None
        self.data["monthly_costs"] = None
        self.data["errors"] = None
        self.data["warnings"] = None
        self.data["insights"] = None
        # Should not raise.
        buf = io.StringIO()
        export_csv.write(self.data, buf)
        rows = list(csv.reader(io.StringIO(buf.getvalue().lstrip("\ufeff"))))
        section_rows = [r[0] for r in rows if r and r[0].startswith("###")]
        for section in CSV_SECTIONS:
            self.assertIn(f"### {section} ###", section_rows)

    def test_to_stdout(self):
        import sys

        captured = io.StringIO()
        real_stdout = sys.stdout
        sys.stdout = captured
        try:
            export_csv.write(self.data, sys.stdout)
        finally:
            sys.stdout = real_stdout
        self.assertTrue(captured.getvalue().startswith("\ufeff"))
        self.assertIn("### Report Metadata ###", captured.getvalue())

    def test_trailing_empty_row(self):
        rows = self._rows()
        self.assertEqual(rows[-1], [])

    def test_forecast_section_present(self):
        rows = self._rows()
        forecast_idx = next(i for i, r in enumerate(rows) if r and r[0] == "### Forecast ###")
        self.assertEqual(
            rows[forecast_idx + 1],
            ["metric", "current", "projected", "limit", "run_out_day"],
        )
        data_rows = [r for r in rows[forecast_idx + 2 :] if r]
        metrics = {r[0] for r in data_rows}
        self.assertIn("minutes", metrics)
        self.assertIn("storage_avg_mb", metrics)
        self.assertIn("premium_requests", metrics)

    def test_write_nested_uses_canonical_column_order(self):
        # Fix #6: values must be looked up by key, not by .values() order,
        # so a dict with keys in a different insertion order doesn't misalign.
        import csv
        import io

        from github_usage.export_csv import _write_nested

        # Second item has keys in a different order than the first
        nested = {
            "sku_a": {"minutes": 10, "cost": 5},
            "sku_b": {"cost": 99, "minutes": 1},  # reversed key order
        }
        buf = io.StringIO()
        writer = csv.writer(buf)
        _write_nested(writer, "section", "sku", nested)
        rows = list(csv.reader(io.StringIO(buf.getvalue())))
        # rows: ["section"], ["sku", "minutes", "cost"], ["sku_a", "10", "5"], ["sku_b", "1", "99"]
        header = rows[1]
        self.assertEqual(header, ["sku", "minutes", "cost"])
        sku_b_row = next(r for r in rows if r[0] == "sku_b")
        # minutes must be in position 1, cost in position 2 — regardless of insertion order
        self.assertEqual(sku_b_row[1], "1")
        self.assertEqual(sku_b_row[2], "99")

    def test_visibility_section_when_split_present(self) -> None:
        self.data["actions"]["private_minutes"] = 900.0
        self.data["actions"]["private_minutes_percent"] = 45.0
        self.data["actions"]["public_minutes"] = 350.0
        self.data["actions"]["unattributed_minutes"] = 0.0
        self.data["actions"]["private_storage_avg_mb"] = 180.0
        self.data["actions"]["public_storage_avg_mb"] = 40.4
        self.data["actions"]["private_storage_gb_hours"] = 100.0
        self.data["actions"]["public_storage_gb_hours"] = 50.0
        self.data["actions"]["unattributed_storage_gb_hours"] = 0.0
        rows = self._rows()
        self.assertIn(["### Actions Usage by Visibility ###"], rows)
        idx = rows.index(["### Actions Usage by Visibility ###"])
        keys = {r[0] for r in rows[idx + 1 :] if r and not r[0].startswith("###")}
        self.assertIn("private_minutes", keys)
        self.assertIn("public_minutes", keys)

    def test_larger_runner_sku_marked(self) -> None:
        self.data["actions"]["sku_breakdown"] = {
            "linux_4_core": {
                "minutes": 10.0,
                "storage_gb_hours": 0.0,
                "gross": 1.0,
                "discount": 0.0,
                "net": 1.0,
                "unitType": "minutes",
            }
        }
        rows = self._rows()
        flat = [item for row in rows for item in row]
        self.assertIn("linux_4_core *", flat)
        self.assertTrue(any("larger runner" in str(item).lower() for item in flat))

    def test_storage_analysis_section(self) -> None:
        self.data["storage_analysis"] = {
            "repos": [
                {
                    "name": "octocat/api",
                    "visibility": "private",
                    "artifact_storage_gb": 0.5,
                    "release_storage_gb": 0.1,
                    "total_storage": 0.6,
                    "artifact_count": 3,
                    "expired_count": 1,
                    "expiring_soon_count": 1,
                    "earliest_expiry": "2026-08-01T00:00:00Z",
                    "retention_days": 90,
                }
            ]
        }
        rows = self._rows()
        self.assertIn(["### Storage Analysis ###"], rows)
        idx = rows.index(["### Storage Analysis ###"])
        self.assertEqual(rows[idx + 1][0], "repo")
        self.assertEqual(rows[idx + 2][0], "octocat/api")
        self.assertEqual(rows[idx + 2][6], "1")  # expired_count

    def test_sources_section_present(self) -> None:
        rows = self._rows()
        self.assertIn(["### Sources ###"], rows)
        idx = rows.index(["### Sources ###"])
        keys = {r[0] for r in rows[idx + 1 :] if r}
        self.assertIn("actions_billing", keys)


if __name__ == "__main__":
    unittest.main()
