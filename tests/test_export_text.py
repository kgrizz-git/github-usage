import io
import unittest

from github_usage import export_text
from tests.conftest import load_export_report_data


class ExportTextTests(unittest.TestCase):
    def setUp(self):
        self.data = load_export_report_data()

    def test_writes_string_data(self):
        buf = io.StringIO()
        export_text.write("Hello, world!\n", buf)
        self.assertEqual(buf.getvalue(), "Hello, world!\n")

    def test_writes_dict_data(self):
        buf = io.StringIO()
        export_text.write(self.data, buf)
        body = buf.getvalue()
        self.assertIn("GitHub Usage Report for octocat", body)
        self.assertIn("Actions", body)

    def test_file_encoding_is_utf8(self):
        import tempfile

        self.data["warnings"] = ["Über cost: $5.00"]
        with tempfile.NamedTemporaryFile(mode="r", encoding="utf-8", delete=False) as f:
            path = f.name
        try:
            with open(path, "w", encoding="utf-8") as f:
                export_text.write(self.data, f)
            with open(path, encoding="utf-8") as f:
                self.assertIn("Über", f.read())
        finally:
            import os

            os.unlink(path)

    def test_to_stdout_string(self):
        import sys

        captured = io.StringIO()
        real_stdout = sys.stdout
        sys.stdout = captured
        try:
            export_text.write("plain text", sys.stdout)
        finally:
            sys.stdout = real_stdout
        self.assertEqual(captured.getvalue(), "plain text\n")

    def test_to_stdout_dict(self):
        import sys

        captured = io.StringIO()
        real_stdout = sys.stdout
        sys.stdout = captured
        try:
            export_text.write(self.data, sys.stdout)
        finally:
            sys.stdout = real_stdout
        self.assertIn("GitHub Usage Report for octocat", captured.getvalue())

    def test_trailing_newline(self):
        buf = io.StringIO()
        export_text.write("no trailing newline", buf)
        self.assertTrue(buf.getvalue().endswith("\n"))

    def test_no_duplicate_newline(self):
        buf = io.StringIO()
        export_text.write("already ends\n", buf)
        self.assertEqual(buf.getvalue(), "already ends\n")


if __name__ == "__main__":
    unittest.main()
