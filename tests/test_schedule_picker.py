"""Tests for SchedulePicker widget."""

from __future__ import annotations

import unittest
from unittest import mock

from github_usage.gui.widgets.schedule_picker import SchedulePicker


@unittest.skipUnless(
    __import__("importlib").util.find_spec("textual") is not None,
    "textual not installed",
)
class SchedulePickerTests(unittest.IsolatedAsyncioTestCase):
    """Mount SchedulePicker and exercise preview/update helpers."""

    async def test_local_preview_updates(self) -> None:
        from textual.app import App, ComposeResult

        class Host(App[None]):
            def compose(self) -> ComposeResult:
                yield SchedulePicker(id="picker", show_local=True, show_ga=False)

        app = Host()
        async with app.run_test():
            picker = app.query_one("#picker", SchedulePicker)
            picker.set_local_schedule(1, 9, 0)
            preview = app.query_one("#local-preview")
            self.assertIn("Mondays", str(preview.render()))

    async def test_ga_cron_round_trip(self) -> None:
        from zoneinfo import ZoneInfo

        from textual.app import App, ComposeResult

        class Host(App[None]):
            def compose(self) -> ComposeResult:
                yield SchedulePicker(id="picker", show_local=False, show_ga=True)

        app = Host()
        async with app.run_test():
            picker = app.query_one("#picker", SchedulePicker)
            tz = ZoneInfo("UTC")
            with mock.patch(
                "github_usage.gui.widgets.schedule_picker.local_timezone", return_value=tz
            ):
                picker.set_ga_cron("0 9 * * 1")
                cron = picker.get_ga_cron()
            self.assertEqual(cron, "0 9 * * 1")


if __name__ == "__main__":
    unittest.main()
