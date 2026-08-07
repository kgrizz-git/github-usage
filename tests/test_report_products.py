import unittest
from contextlib import redirect_stdout
from io import StringIO
from unittest import mock


class ProductsReportTests(unittest.TestCase):
    def test_show_copilot_summary_prints_totals(self):
        from github_usage.report_products import show_copilot_summary

        api = mock.Mock()
        summary = {
            "items": {
                "copilot": {
                    "grossQuantity": 1,
                    "grossAmount": 10.0,
                    "discountAmount": 2.0,
                    "netAmount": 8.0,
                    "pricePerUnit": 10.0,
                    "unitType": "reqs",
                }
            }
        }

        with (
            mock.patch("github_usage.report_products.get_billing_summary", return_value=summary),
            mock.patch("github_usage.report_products.get_premium_request_usage", return_value={}),
        ):
            stdout = StringIO()
            with redirect_stdout(stdout):
                show_copilot_summary(api, "octocat")

            output = stdout.getvalue()
            self.assertIn("gross: $10.0000", output)
            self.assertIn("net: $8.0000", output)

    def test_show_base_costs_handles_missing_items_key(self):
        from github_usage.report_products import show_base_costs

        api = mock.Mock()
        stdout = StringIO()
        with redirect_stdout(stdout):
            # Pass dicts without "items" key to ensure it doesn't raise KeyError
            show_base_costs(api, "octocat", {}, {}, {})

        output = stdout.getvalue()
        self.assertIn("Base Costs", output)
