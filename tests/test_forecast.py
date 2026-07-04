"""Tests for pure forecast computation."""

from __future__ import annotations

import unittest

from github_usage.forecast import compute_forecast


class ComputeForecastTests(unittest.TestCase):
    def test_compute_forecast_mid_month(self):
        forecast = compute_forecast(
            day_of_month=15,
            days_in_month=31,
            minutes=823.0,
            minutes_limit=2000.0,
            storage_avg_mb=145.2,
            storage_limit_mb=500.0,
            premium_requests=120.0,
            premium_requests_limit=1000.0,
        )
        self.assertIsNotNone(forecast)
        assert forecast is not None
        self.assertEqual(forecast["day_of_month"], 15)
        self.assertEqual(forecast["days_in_month"], 31)
        self.assertAlmostEqual(forecast["minutes"]["current"], 823.0)
        self.assertAlmostEqual(forecast["minutes"]["projected"], 823.0 * 31 / 15)
        self.assertAlmostEqual(forecast["storage_avg_mb"]["current"], 145.2)
        self.assertAlmostEqual(forecast["storage_avg_mb"]["projected"], 145.2 * 31 / 15)
        self.assertAlmostEqual(forecast["premium_requests"]["current"], 120.0)
        self.assertAlmostEqual(forecast["premium_requests"]["projected"], 120.0 * 31 / 15)

    def test_compute_forecast_first_day(self):
        forecast = compute_forecast(
            day_of_month=1,
            days_in_month=31,
            minutes=10.0,
            minutes_limit=2000.0,
            storage_avg_mb=5.0,
            storage_limit_mb=500.0,
            premium_requests=1.0,
            premium_requests_limit=1000.0,
        )
        self.assertIsNone(forecast)

    def test_compute_forecast_run_out(self):
        forecast = compute_forecast(
            day_of_month=15,
            days_in_month=31,
            minutes=1000.0,
            minutes_limit=2000.0,
            storage_avg_mb=250.0,
            storage_limit_mb=500.0,
            premium_requests=600.0,
            premium_requests_limit=1000.0,
        )
        self.assertIsNotNone(forecast)
        assert forecast is not None
        self.assertEqual(forecast["minutes"]["run_out_day"], 30)
        self.assertEqual(forecast["storage_avg_mb"]["run_out_day"], 30)
        self.assertEqual(forecast["premium_requests"]["run_out_day"], 25)

    def test_compute_forecast_exactly_at_limit(self):
        forecast = compute_forecast(
            day_of_month=15,
            days_in_month=31,
            minutes=2000.0 * 15 / 31,
            minutes_limit=2000.0,
            storage_avg_mb=0.0,
            storage_limit_mb=500.0,
            premium_requests=0.0,
            premium_requests_limit=None,
        )
        self.assertIsNotNone(forecast)
        assert forecast is not None
        self.assertAlmostEqual(forecast["minutes"]["projected"], 2000.0)
        self.assertEqual(forecast["minutes"]["run_out_day"], 31)

    def test_compute_forecast_unknown_limit(self):
        forecast = compute_forecast(
            day_of_month=15,
            days_in_month=31,
            minutes=100.0,
            minutes_limit=2000.0,
            storage_avg_mb=50.0,
            storage_limit_mb=500.0,
            premium_requests=100.0,
            premium_requests_limit=None,
        )
        self.assertIsNotNone(forecast)
        assert forecast is not None
        self.assertIsNone(forecast["premium_requests"]["limit"])
        self.assertIsNone(forecast["premium_requests"]["run_out_day"])

    def test_compute_forecast_last_day(self):
        forecast = compute_forecast(
            day_of_month=31,
            days_in_month=31,
            minutes=500.0,
            minutes_limit=2000.0,
            storage_avg_mb=100.0,
            storage_limit_mb=500.0,
            premium_requests=50.0,
            premium_requests_limit=1000.0,
        )
        self.assertIsNotNone(forecast)
        assert forecast is not None
        self.assertAlmostEqual(forecast["minutes"]["projected"], 500.0)
        self.assertAlmostEqual(forecast["storage_avg_mb"]["projected"], 100.0)
        self.assertAlmostEqual(forecast["premium_requests"]["projected"], 50.0)

    def test_compute_forecast_last_day_already_over(self):
        forecast = compute_forecast(
            day_of_month=31,
            days_in_month=31,
            minutes=2500.0,
            minutes_limit=2000.0,
            storage_avg_mb=0.0,
            storage_limit_mb=500.0,
            premium_requests=0.0,
            premium_requests_limit=None,
        )
        self.assertIsNotNone(forecast)
        assert forecast is not None
        self.assertEqual(forecast["minutes"]["run_out_day"], 25)

    def test_compute_forecast_skipped_before_day_3(self):
        for day in (1, 2):
            with self.subTest(day=day):
                forecast = compute_forecast(
                    day_of_month=day,
                    days_in_month=31,
                    minutes=100.0,
                    minutes_limit=2000.0,
                    storage_avg_mb=50.0,
                    storage_limit_mb=500.0,
                    premium_requests=10.0,
                    premium_requests_limit=1000.0,
                )
                self.assertIsNone(forecast)

    def test_compute_forecast_invalid_date(self):
        forecast = compute_forecast(
            day_of_month=32,
            days_in_month=31,
            minutes=100.0,
            minutes_limit=2000.0,
            storage_avg_mb=50.0,
            storage_limit_mb=500.0,
            premium_requests=10.0,
            premium_requests_limit=1000.0,
        )
        self.assertIsNone(forecast)

    def test_compute_forecast_zero_current_value(self):
        forecast = compute_forecast(
            day_of_month=15,
            days_in_month=31,
            minutes=0.0,
            minutes_limit=2000.0,
            storage_avg_mb=50.0,
            storage_limit_mb=500.0,
            premium_requests=10.0,
            premium_requests_limit=1000.0,
        )
        self.assertIsNotNone(forecast)
        assert forecast is not None
        self.assertIsNone(forecast["minutes"]["run_out_day"])
        self.assertEqual(forecast["minutes"]["projected"], 0.0)

    def test_compute_forecast_skip_all_zero(self):
        forecast = compute_forecast(
            day_of_month=15,
            days_in_month=31,
            minutes=0.0,
            minutes_limit=2000.0,
            storage_avg_mb=0.0,
            storage_limit_mb=500.0,
            premium_requests=0.0,
            premium_requests_limit=1000.0,
        )
        self.assertIsNone(forecast)


if __name__ == "__main__":
    unittest.main()
