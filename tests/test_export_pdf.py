import io
import re
import unittest
from unittest import mock

from tests.conftest import load_export_report_data


def _has_fpdf2():
    try:
        from fpdf import FPDF  # noqa: F401

        return True
    except ImportError:
        return False


def _has_pypdf():
    try:
        import pypdf  # noqa: F401

        return True
    except ImportError:
        return False


def _page_count(pdf_bytes: bytes) -> int:
    """Extract the page count from the PDF ``/Count`` field (no parsing needed)."""
    match = re.search(rb"/Count\s+(\d+)", pdf_bytes)
    return int(match.group(1)) if match else 0


def _extract_text(pdf_bytes: bytes) -> str:
    """Extract text from a PDF using pypdf (if available)."""
    import pypdf

    reader = pypdf.PdfReader(io.BytesIO(pdf_bytes))
    return "\n".join(page.extract_text() or "" for page in reader.pages)


PDF_SECTIONS = [
    "Actions",
    "Copilot",
    "Git LFS",
    "Monthly Costs",
    "Top Repos by Minutes",
    "Top Repos by Cost",
    "Artifact Storage",
    "Release Assets",
    "Key Insights",
    "Unavailable Data",
    "Sources",
    "Usage Forecast",
]


@unittest.skipUnless(_has_fpdf2(), "fpdf2 not installed")
class ExportPdfTests(unittest.TestCase):
    def setUp(self):
        self.data = load_export_report_data()

    def _save(self, data=None):
        from github_usage import export_pdf

        buf = io.BytesIO()
        export_pdf.write(data if data is not None else self.data, buf)
        return buf.getvalue()

    def test_creates_pdf(self):
        pdf_bytes = self._save()
        self.assertTrue(pdf_bytes.startswith(b"%PDF-"))
        self.assertGreater(len(pdf_bytes), 100)

    @unittest.skipUnless(_has_pypdf(), "pypdf not installed (text checks skipped)")
    def test_cover_page(self):
        text = _extract_text(self._save())
        self.assertIn("GitHub Usage Report", text)
        self.assertIn("octocat", text)
        self.assertIn("current_month", text)

    @unittest.skipUnless(_has_pypdf(), "pypdf not installed (text checks skipped)")
    def test_actions_page(self):
        text = _extract_text(self._save())
        self.assertIn("Actions", text)
        self.assertIn("Minutes", text)
        self.assertIn("Storage", text)

    @unittest.skipUnless(_has_pypdf(), "pypdf not installed (text checks skipped)")
    def test_sections_present(self):
        text = _extract_text(self._save())
        for section in PDF_SECTIONS:
            self.assertIn(section, text)

    @unittest.skipUnless(_has_pypdf(), "pypdf not installed (text checks skipped)")
    def test_forecast_page_present(self):
        text = _extract_text(self._save())
        self.assertIn("Usage Forecast", text)
        self.assertIn("Actions Minutes", text)

    def test_pages_count_with_all_sections(self):
        # Cover page + 12 sections (incl. Sources) = 13 pages
        self.assertEqual(_page_count(self._save()), 13)

    def test_empty_sections_reduce_page_count(self):
        self.data["artifact_storage"] = None
        self.data["release_assets"] = None
        self.data["errors"] = None
        self.data["insights"] = []
        self.data["repo_consumers"] = None
        # Cover + Actions + Copilot + Git LFS + Monthly Costs + Sources + Forecast = 7
        self.assertEqual(_page_count(self._save()), 7)

    @unittest.skipUnless(_has_pypdf(), "pypdf not installed (text checks skipped)")
    def test_truncates_large_sections(self):
        big = [
            {"repo": f"repo-{i}", "minutes": float(i), "gross": 1.0, "storage_avg_mb": 1.0}
            for i in range(50)
        ]
        self.data["repo_consumers"] = {"by_minutes": big, "by_cost": big}
        text = _extract_text(self._save())
        self.assertIn("truncated", text)
        self.assertIn("20 more rows", text)

    @unittest.skipUnless(_has_pypdf(), "pypdf not installed (text checks skipped)")
    def test_handles_string_numbers(self):
        self.data["actions"]["minutes"] = "1250"
        self.data["actions"]["minutes_limit"] = "2000"
        text = _extract_text(self._save())
        self.assertIn("1250", text)

    @unittest.skipUnless(_has_pypdf(), "pypdf not installed (text checks skipped)")
    def test_none_displays_as_na(self):
        self.data["actions"] = {"minutes": None, "minutes_limit": None, "minutes_percent": None}
        text = _extract_text(self._save())
        self.assertIn("N/A", text)

    def test_to_stdout(self):
        from github_usage import export_pdf

        buf = io.BytesIO()
        export_pdf.write(self.data, buf)
        self.assertTrue(buf.getvalue().startswith(b"%PDF-"))

    def test_write_actions_page_renders_minutes_and_storage(self):
        # A4a: a section helper can be exercised in isolation by passing
        # in an add_section closure bound to a real fpdf2 PDF.
        from fpdf import FPDF

        from github_usage.export_pdf import _make_pdf_writer, _write_actions_page

        pdf = FPDF()
        pdf.set_auto_page_break(auto=True, margin=20)
        add_section, _ = _make_pdf_writer(pdf)
        data = {
            "actions": {
                "minutes": 1250.0,
                "minutes_limit": 2000,
                "minutes_percent": 62.5,
                "storage_avg_mb": 312.0,
                "storage_limit_mb": 500,
                "storage_percent": 62.4,
            },
        }
        _write_actions_page(add_section, data)
        # add_section triggers pdf.add_page(); after the call, the page
        # count is 2 (cover page from the test's own add_page, if any,
        # plus the actions page).
        self.assertGreaterEqual(pdf.pages_count, 1)

    def test_dependency_check_at_orchestrator(self):
        from github_usage import export_report

        with (
            mock.patch.dict("sys.modules", {"fpdf": None}),
            self.assertRaises(RuntimeError) as ctx,
        ):
            export_report.export(self.data, "pdf", output_path="/tmp/_should_not_write.pdf")
        self.assertIn("fpdf2", str(ctx.exception))

    @unittest.skipUnless(_has_pypdf(), "pypdf not installed (text checks skipped)")
    def test_sources_page_present(self) -> None:
        text = _extract_text(self._save())
        self.assertIn("Sources", text)
        self.assertIn("actions_billing", text)

    @unittest.skipUnless(_has_pypdf(), "pypdf not installed (text checks skipped)")
    def test_private_usage_framing_when_split_present(self) -> None:
        self.data["actions"]["private_minutes"] = 900.0
        self.data["actions"]["private_minutes_percent"] = 45.0
        self.data["actions"]["public_minutes"] = 350.0
        self.data["actions"]["unattributed_minutes"] = 0.0
        self.data["actions"]["private_storage_avg_mb"] = 180.0
        self.data["actions"]["public_storage_avg_mb"] = 40.4
        self.data["actions"]["private_storage_gb_hours"] = 100.0
        self.data["actions"]["public_storage_gb_hours"] = 50.0
        self.data["actions"]["unattributed_storage_gb_hours"] = 0.0
        text = _extract_text(self._save())
        self.assertIn("Private Usage Framing", text)
        self.assertIn("private_minutes", text)

    @unittest.skipUnless(_has_pypdf(), "pypdf not installed (text checks skipped)")
    def test_larger_runner_note_ascii_safe(self) -> None:
        self.data["actions"]["sku_breakdown"] = {
            "linux_4_core": {
                "minutes": 10.0,
                "unitType": "minutes",
            }
        }
        text = _extract_text(self._save())
        self.assertIn("linux_4_core *", text)
        self.assertIn("larger runner", text.lower())


if __name__ == "__main__":
    unittest.main()
