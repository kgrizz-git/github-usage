import io
import json
import os
import tempfile
import unittest
from unittest import mock

from github_usage import export_json, export_report
from github_usage.redact import REDACT_REPO, REDACT_USERNAME
from tests.conftest import load_export_report_data


class ExportReportRoutingTests(unittest.TestCase):
    def setUp(self):
        self.data = load_export_report_data()
        self.tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        import shutil

        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _write(self, fmt, **kwargs):
        return export_report.export(
            self.data, fmt, output_path=os.path.join(self.tmpdir, f"out.{fmt}"), **kwargs
        )

    def test_routes_csv(self):
        path = self._write("csv", redact_data=False)
        with open(path, encoding="utf-8") as f:
            content = f.read()
        self.assertIn("### Report Metadata ###", content)
        self.assertIn("octocat", content)

    def test_routes_json(self):
        path = self._write("json", redact_data=False)
        with open(path, encoding="utf-8") as f:
            data = json.loads(f.read())
        self.assertEqual(data["username"], "octocat")

    def test_routes_text(self):
        path = self._write("text", redact_data=False)
        with open(path, encoding="utf-8") as f:
            self.assertIn("GitHub Usage Report for octocat", f.read())

    def test_raises_on_unknown_format(self):
        with self.assertRaises(ValueError):
            export_report.export(self.data, "xml", output_path=os.path.join(self.tmpdir, "out.xml"))

    def test_raises_on_text_data_with_xlsx(self):
        with self.assertRaisesRegex(ValueError, "requires structured dict"):
            export_report.export(
                "plain text", "xlsx", output_path=os.path.join(self.tmpdir, "out.xlsx")
            )

    def test_raises_on_text_data_with_pdf(self):
        with self.assertRaisesRegex(ValueError, "requires structured dict"):
            export_report.export(
                "plain text", "pdf", output_path=os.path.join(self.tmpdir, "out.pdf")
            )

    def test_raises_on_text_data_with_csv(self):
        with self.assertRaisesRegex(ValueError, "requires structured dict"):
            export_report.export(
                "plain text", "csv", output_path=os.path.join(self.tmpdir, "out.csv")
            )


class ExportReportDependencyTests(unittest.TestCase):
    def setUp(self):
        self.data = load_export_report_data()
        self.tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        import shutil

        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_raises_on_missing_xlsx_dep(self):
        with (
            mock.patch.dict("sys.modules", {"openpyxl": None}),
            self.assertRaises(RuntimeError) as ctx,
        ):
            export_report.export(
                self.data, "xlsx", output_path=os.path.join(self.tmpdir, "out.xlsx")
            )
        self.assertIn("openpyxl", str(ctx.exception))
        self.assertIn("export-xlsx", str(ctx.exception))

    def test_raises_on_missing_pdf_dep(self):
        with (
            mock.patch.dict("sys.modules", {"fpdf": None}),
            self.assertRaises(RuntimeError) as ctx,
        ):
            export_report.export(self.data, "pdf", output_path=os.path.join(self.tmpdir, "out.pdf"))
        self.assertIn("fpdf2", str(ctx.exception))
        self.assertIn("export-pdf", str(ctx.exception))


class ExportReportNoneAndRedactionTests(unittest.TestCase):
    def setUp(self):
        self.data = load_export_report_data()
        self.tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        import shutil

        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_none_returns_empty_string(self):
        self.assertEqual(export_report.export(self.data, "none"), "")

    def test_redacts_dict_data(self):
        path = export_report.export(
            self.data, "json", output_path=os.path.join(self.tmpdir, "out.json")
        )
        with open(path, encoding="utf-8") as f:
            result = json.loads(f.read())
        self.assertEqual(result["username"], REDACT_USERNAME)
        for entry in result["repo_consumers"]["by_minutes"]:
            self.assertEqual(entry["repo"], REDACT_REPO)

    def test_redacts_string_data(self):
        body = "Contact me at user@example.com or pay $10.00."
        path = export_report.export(body, "text", output_path=os.path.join(self.tmpdir, "out.txt"))
        with open(path, encoding="utf-8") as f:
            result = f.read()
        self.assertIn("[redacted-email]", result)
        self.assertIn("[redacted-amount]", result)
        self.assertNotIn("user@example.com", result)

    def test_skips_redaction_when_disabled(self):
        path = export_report.export(
            self.data, "json", output_path=os.path.join(self.tmpdir, "out.json"), redact_data=False
        )
        with open(path, encoding="utf-8") as f:
            result = json.loads(f.read())
        self.assertEqual(result["username"], "octocat")


class ExportReportAtomicWriteTests(unittest.TestCase):
    def setUp(self):
        self.data = load_export_report_data()
        self.tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        import shutil

        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_atomic_write_on_success(self):
        path = os.path.join(self.tmpdir, "out.json")
        export_report.export(self.data, "json", output_path=path)
        self.assertTrue(os.path.exists(path))
        # No leftover .tmp files
        leftovers = [f for f in os.listdir(self.tmpdir) if f.endswith(".tmp")]
        self.assertEqual(leftovers, [])

    def test_cleanup_on_failure(self):
        path = os.path.join(self.tmpdir, "out.json")
        with (
            mock.patch.object(export_json, "write", side_effect=RuntimeError("boom")),
            self.assertRaises(RuntimeError),
        ):
            export_report.export(self.data, "json", output_path=path)
        self.assertFalse(os.path.exists(path))
        leftovers = [f for f in os.listdir(self.tmpdir) if f.endswith(".tmp")]
        self.assertEqual(leftovers, [])


class ExportReportStdoutTests(unittest.TestCase):
    def setUp(self):
        self.data = load_export_report_data()

    def test_writes_to_stdout_json(self):
        import sys

        captured = io.StringIO()
        real_stdout = sys.stdout
        sys.stdout = captured
        try:
            result = export_report.export(self.data, "json", to_stdout=True, redact_data=False)
        finally:
            sys.stdout = real_stdout
        self.assertEqual(result, "")
        data = json.loads(captured.getvalue())
        self.assertEqual(data["username"], "octocat")


class ExportReportFilenameTests(unittest.TestCase):
    def test_generate_filename_defaults(self):
        with mock.patch.object(export_report.datetime, "datetime") as dt:
            dt.now.return_value.strftime.return_value = "2026-06-15"
            self.assertEqual(export_report.generate_filename("csv"), "github-usage-2026-06-15.csv")

    def test_generate_filename_with_username(self):
        with mock.patch.object(export_report.datetime, "datetime") as dt:
            dt.now.return_value.strftime.return_value = "2026-06-15"
            self.assertEqual(
                export_report.generate_filename("csv", username="octocat"),
                "github-usage-octocat-2026-06-15.csv",
            )

    def test_generate_filename_with_month(self):
        self.assertEqual(
            export_report.generate_filename("csv", month="2026-05"),
            "github-usage-2026-05.csv",
        )

    def test_generate_filename_with_username_and_month(self):
        self.assertEqual(
            export_report.generate_filename("csv", username="octocat", month="2026-05"),
            "github-usage-octocat-2026-05.csv",
        )

    def test_generate_filename_extensions(self):
        with mock.patch.object(export_report.datetime, "datetime") as dt:
            dt.now.return_value.strftime.return_value = "2026-06-15"
            for fmt, ext in [
                ("json", "json"),
                ("text", "txt"),
                ("csv", "csv"),
                ("xlsx", "xlsx"),
                ("pdf", "pdf"),
            ]:
                self.assertTrue(export_report.generate_filename(fmt).endswith(f".{ext}"))


if __name__ == "__main__":
    unittest.main()
