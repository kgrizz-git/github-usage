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
