"""Tests for Copilot metering presentation helpers."""

from __future__ import annotations

import unittest

from github_usage.copilot_metering import copilot_forecast_metric, copilot_usage_summary_lines


class CopilotMeteringTests(unittest.TestCase):
    def test_forecast_uses_credit_quantity_not_dollar_net(self):
        copilot = {
            "metering": "ai_credits",
            "total_credits_used": 3956.18,
            "total_net": 0.0,
        }
        value, label = copilot_forecast_metric(copilot)
        self.assertAlmostEqual(value, 3956.18)
        self.assertIn("qty", label.lower())

    def test_summary_shows_credit_quantity(self):
        lines = copilot_usage_summary_lines(
            {
                "metering": "ai_credits",
                "total_credits_used": 100.0,
                "total_net": 0.0,
            }
        )
        joined = "\n".join(lines)
        self.assertIn("100.00", joined)
        self.assertNotIn("billing units", joined)


if __name__ == "__main__":
    unittest.main()
