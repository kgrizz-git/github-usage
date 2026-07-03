"""Tests for schedule_helpers."""

from __future__ import annotations

import unittest
from datetime import datetime
from unittest import mock
from zoneinfo import ZoneInfo

from github_usage import cli_runs, schedule_helpers


class BuildWeeklyCronUtcTests(unittest.TestCase):
    """Local weekly time → UTC cron conversion."""

    def test_utc_timezone_identity(self):
        tz = ZoneInfo("UTC")
        self.assertEqual(
            schedule_helpers.build_weekly_cron_utc(1, 9, 0, tz),
            "0 9 * * 1",
        )

    def test_new_york_monday_morning_winter(self):
        tz = ZoneInfo("America/New_York")
        frozen = datetime(2024, 1, 15, 12, 0, tzinfo=tz)
        with mock.patch("github_usage.schedule_helpers.datetime") as mock_dt:
            mock_dt.now.return_value = frozen
            mock_dt.side_effect = lambda *a, **k: datetime(*a, **k)
            cron = schedule_helpers.build_weekly_cron_utc(1, 9, 0, tz)
        self.assertEqual(cron, "0 14 * * 1")

    def test_local_evening_crosses_utc_midnight(self):
        """Monday 22:00 US Eastern (winter) → Tuesday 03:00 UTC."""
        tz = ZoneInfo("America/New_York")
        frozen = datetime(2024, 1, 15, 12, 0, tzinfo=tz)
        with mock.patch("github_usage.schedule_helpers.datetime") as mock_dt:
            mock_dt.now.return_value = frozen
            mock_dt.side_effect = lambda *a, **k: datetime(*a, **k)
            cron = schedule_helpers.build_weekly_cron_utc(1, 22, 0, tz)
        self.assertEqual(cron, "0 3 * * 2")


class ParseWeeklyCronToLocalTests(unittest.TestCase):
    """UTC cron → local weekly time."""

    def test_round_trip_utc(self):
        tz = ZoneInfo("UTC")
        cron = "0 9 * * 1"
        parsed = schedule_helpers.parse_weekly_cron_to_local(cron, tz)
        self.assertEqual(parsed, (1, 9, 0))
        self.assertEqual(
            schedule_helpers.build_weekly_cron_utc(1, 9, 0, tz),
            cron,
        )

    def test_round_trip_new_york_winter(self):
        tz = ZoneInfo("America/New_York")
        cron = "0 14 * * 1"
        parsed = schedule_helpers.parse_weekly_cron_to_local(cron, tz)
        self.assertEqual(parsed, (1, 9, 0))

    def test_daily_returns_none(self):
        self.assertIsNone(schedule_helpers.parse_weekly_cron_to_local("30 14 * * *"))

    def test_complex_returns_none(self):
        self.assertIsNone(schedule_helpers.parse_weekly_cron_to_local("*/15 9 * * 1-5"))


class DescribeCronHumanTests(unittest.TestCase):
    """Human-readable cron translation."""

    def test_weekly_monday_morning(self):
        self.assertEqual(
            schedule_helpers.describe_cron_human("0 9 * * 1"),
            "Mondays at 09:00 UTC",
        )

    def test_weekly_friday(self):
        self.assertEqual(
            schedule_helpers.describe_cron_human("0 8 * * 5"),
            "Fridays at 08:00 UTC",
        )

    def test_daily(self):
        self.assertEqual(
            schedule_helpers.describe_cron_human("30 14 * * *"),
            "Daily at 14:30 UTC",
        )

    def test_monthly_day(self):
        self.assertEqual(
            schedule_helpers.describe_cron_human("0 9 15 * *"),
            "Day 15 of each month at 09:00 UTC",
        )

    def test_complex_returns_none(self):
        self.assertIsNone(schedule_helpers.describe_cron_human("*/15 9 * * 1-5"))

    def test_cli_runs_reexport(self):
        self.assertIs(cli_runs.describe_cron_human, schedule_helpers.describe_cron_human)


class DescribeLocalScheduleTests(unittest.TestCase):
    def test_monday_morning(self):
        self.assertEqual(
            schedule_helpers.describe_local_schedule(1, 9, 0),
            "Mondays at 09:00 local time",
        )


if __name__ == "__main__":
    unittest.main()
