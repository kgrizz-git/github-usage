import csv
import io
import unittest

from github_usage import export_csv
from tests.conftest import load_export_report_data

CSV_SECTIONS = [
    "Report Metadata",
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
]


class ExportCsvTests(unittest.TestCase):
    def setUp(self):
        self.data = load_export_report_data()

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
        self.assertIn("enterprise", data_rows)
        self.assertIn("free", data_rows)

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


if __name__ == "__main__":
    unittest.main()
