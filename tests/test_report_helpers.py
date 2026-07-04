"""Tests for shared report helpers."""

from __future__ import annotations

import unittest
from datetime import date

from github_usage.report_helpers import day_of_month, days_in_month, hours_in_month


class DateHelperTests(unittest.TestCase):
    def test_days_in_month_january(self):
        self.assertEqual(days_in_month(date(2026, 1, 15)), 31)

    def test_days_in_month_february_non_leap(self):
        self.assertEqual(days_in_month(date(2025, 2, 15)), 28)

    def test_days_in_month_february_leap(self):
        self.assertEqual(days_in_month(date(2024, 2, 15)), 29)

    def test_days_in_month_defaults_to_today(self):
        result = days_in_month()
        self.assertEqual(result, days_in_month(date.today()))

    def test_day_of_month(self):
        self.assertEqual(day_of_month(date(2026, 7, 15)), 15)

    def test_day_of_month_defaults_to_today(self):
        self.assertEqual(day_of_month(), date.today().day)

    def test_hours_in_month(self):
        self.assertEqual(hours_in_month(date(2026, 1, 15)), 31 * 24)


if __name__ == "__main__":
    unittest.main()
