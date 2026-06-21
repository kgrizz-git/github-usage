import unittest
from contextlib import redirect_stdout
from io import StringIO


class SummaryTests(unittest.TestCase):
    def test_print_cost_overview_handles_zero_gross(self):
        from github_usage.report_summary import _print_cost_overview

        stdout = StringIO()
        with redirect_stdout(stdout):
            _print_cost_overview(0.0, 0.0, 0.0)

        output = stdout.getvalue()
        self.assertIn("Total Gross:          $0.0000", output)
        self.assertIn("(0.0% off)", output)

    def test_print_utilization_handles_zero_minutes(self):
        from github_usage.report_summary import _print_utilization

        stdout = StringIO()
        with redirect_stdout(stdout):
            _print_utilization(0.0, 0.0)

        output = stdout.getvalue()
        self.assertIn("Actions Minutes:          0.0 / 2000 min (0.0% of free tier)", output)
        self.assertIn("░" * 40, output)

    def test_print_recommendations_detects_high_usage(self):
        from github_usage.report_summary import _print_recommendations

        stdout = StringIO()
        with redirect_stdout(stdout):
            # 1800 mins is 90% of 2000
            _print_recommendations(1800, [], {}, None, {})

        output = stdout.getvalue()
        self.assertIn("Upgrade from free tier", output)

    def test_print_utilization_caps_bar_at_40_chars_when_over_100_pct(self):
        from github_usage.report_summary import _print_utilization

        # 3000 minutes = 150% of the 2000-minute free tier — bar must not exceed 40 chars
        stdout = StringIO()
        with redirect_stdout(stdout):
            _print_utilization(3000.0, 0.0)

        output = stdout.getvalue()
        bar_line = next(line for line in output.splitlines() if "█" in line)
        filled = bar_line.count("█")
        empty = bar_line.strip().count("░")
        self.assertEqual(filled + empty, 40)
        self.assertEqual(filled, 40)

    def test_print_utilization_storage_caps_bar_at_40_chars_when_over_100_pct(self):
        from github_usage.report_summary import _print_utilization

        # 1000 MB average storage = 200% of the 500 MB free tier
        # gb_hours_to_avg_mb(x) = x * 1024 / (24 * 30); solve for x giving ~1000 MB
        # 1000 * 24 * 30 / 1024 ≈ 703 gb_hours
        storage_gb_hours = 1000 * 24 * 30 / 1024
        stdout = StringIO()
        with redirect_stdout(stdout):
            _print_utilization(0.0, storage_gb_hours)

        output = stdout.getvalue()
        bar_lines = [line for line in output.splitlines() if "█" in line or "░" in line]
        storage_bar = bar_lines[-1]
        filled = storage_bar.count("█")
        empty = storage_bar.strip().count("░")
        self.assertEqual(filled + empty, 40)
        self.assertEqual(filled, 40)
