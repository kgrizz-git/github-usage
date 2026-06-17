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

    def test_pages_count_with_all_sections(self):
        # Cover page + 10 sections = 11 pages
        self.assertEqual(_page_count(self._save()), 11)

    def test_empty_sections_reduce_page_count(self):
        self.data["artifact_storage"] = None
        self.data["release_assets"] = None
        self.data["errors"] = None
        self.data["insights"] = []
        self.data["repo_consumers"] = None
        # Cover + Actions + Copilot + Git LFS + Monthly Costs = 5
        self.assertEqual(_page_count(self._save()), 5)

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

    def test_dependency_check_at_orchestrator(self):
        from github_usage import export_report

        with (
            mock.patch.dict("sys.modules", {"fpdf": None}),
            self.assertRaises(RuntimeError) as ctx,
        ):
            export_report.export(self.data, "pdf", output_path="/tmp/_should_not_write.pdf")
        self.assertIn("fpdf2", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
