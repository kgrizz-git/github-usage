"""Tests for the report-dict forecast adapter."""

from __future__ import annotations

import unittest
from datetime import date

from github_usage.report_forecast_data import build_report_forecast


class BuildReportForecastTests(unittest.TestCase):
    def test_reads_actions_and_copilot_values(self):
        report = {
            "actions": {
                "minutes": 100.0,
                "storage_avg_mb": 50.0,
                "minutes_limit": 2000.0,
                "storage_limit_mb": 500.0,
            },
            "copilot": {"total_requests": 25.0},
        }
        forecast = build_report_forecast(
            report, premium_requests_limit=1000.0, reference_date=date(2026, 7, 15)
        )
        self.assertIsNotNone(forecast)
        assert forecast is not None
        self.assertEqual(forecast["day_of_month"], 15)
        self.assertEqual(forecast["days_in_month"], 31)
        self.assertEqual(forecast["minutes"]["current"], 100.0)
        self.assertEqual(forecast["storage_avg_mb"]["current"], 50.0)
        self.assertEqual(forecast["premium_requests"]["current"], 25.0)
        self.assertEqual(forecast["premium_requests"]["limit"], 1000.0)

    def test_missing_sections_default_to_zero(self):
        forecast = build_report_forecast(
            {}, premium_requests_limit=1000.0, reference_date=date(2026, 7, 15)
        )
        self.assertIsNone(forecast)

    def test_default_limits_when_actions_absent(self):
        forecast = build_report_forecast(
            {"copilot": {"total_requests": 100.0}},
            premium_requests_limit=1000.0,
            reference_date=date(2026, 7, 15),
        )
        self.assertIsNotNone(forecast)
        assert forecast is not None
        self.assertEqual(forecast["minutes"]["limit"], 2000.0)
        self.assertEqual(forecast["storage_avg_mb"]["limit"], 500.0)

    def test_premium_requests_limit_threaded_through(self):
        report = {
            "actions": {"minutes": 100.0, "storage_avg_mb": 0.0},
            "copilot": {"total_requests": 10.0},
        }
        forecast = build_report_forecast(
            report, premium_requests_limit=500.0, reference_date=date(2026, 7, 15)
        )
        self.assertIsNotNone(forecast)
        assert forecast is not None
        self.assertEqual(forecast["premium_requests"]["limit"], 500.0)

    def test_reference_date_controls_day_count(self):
        report = {
            "actions": {"minutes": 100.0, "storage_avg_mb": 0.0},
            "copilot": {"total_requests": 10.0},
        }
        forecast = build_report_forecast(
            report, premium_requests_limit=None, reference_date=date(2026, 2, 15)
        )
        self.assertIsNotNone(forecast)
        assert forecast is not None
        self.assertEqual(forecast["day_of_month"], 15)
        self.assertEqual(forecast["days_in_month"], 28)

    def test_returns_none_when_all_current_values_zero(self):
        report = {
            "actions": {"minutes": 0.0, "storage_avg_mb": 0.0},
            "copilot": {"total_requests": 0.0},
        }
        forecast = build_report_forecast(report, reference_date=date(2026, 7, 15))
        self.assertIsNone(forecast)

    def test_none_values_coerced_to_zero(self):
        report = {
            "actions": {
                "minutes": None,
                "storage_avg_mb": 50.0,
                "minutes_limit": None,
                "storage_limit_mb": None,
            },
            "copilot": {"total_requests": 10.0},
        }
        forecast = build_report_forecast(report, reference_date=date(2026, 7, 15))
        self.assertIsNotNone(forecast)
        assert forecast is not None
        self.assertEqual(forecast["minutes"]["current"], 0.0)
        self.assertEqual(forecast["minutes"]["limit"], 2000.0)
        self.assertEqual(forecast["storage_avg_mb"]["limit"], 500.0)


if __name__ == "__main__":
    unittest.main()
