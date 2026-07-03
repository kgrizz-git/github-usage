"""Tests for keyboard scroll routing."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from github_usage.gui.scroll_actions import scroll_target
from github_usage.gui_backend import load_profiles, load_setup_paths, save_profiles, write_secrets


def _paths():
    tmp = tempfile.TemporaryDirectory()
    paths = load_setup_paths(Path(tmp.name))
    write_secrets(
        paths,
        {
            "GITHUB_TOKEN": "ghp_test",
            "RESEND_API_KEY": "re_test",
            "REPORT_EMAIL": "user@example.com",
            "RESEND_FROM": "from@example.com",
        },
    )
    save_profiles(paths, load_profiles(paths))
    return tmp, paths


@unittest.skipUnless(
    __import__("importlib").util.find_spec("textual") is not None,
    "textual not installed",
)
class ScrollActionsTests(unittest.IsolatedAsyncioTestCase):
    async def test_scroll_target_is_active_view(self) -> None:
        from github_usage.gui.app import GitHubUsageApp
        from github_usage.gui.views.schedules_view import SchedulesView

        tmp, paths = _paths()
        self.addCleanup(tmp.cleanup)
        with mock.patch("github_usage.gui.state.load_setup_paths", return_value=paths):
            app = GitHubUsageApp()

        async with app.run_test(size=(100, 32)) as pilot:
            await pilot.pause(0.05)
            main = app.query_one("MainWindow")
            main.action_show_view("schedules")
            target = scroll_target(app)
            self.assertIsInstance(target, SchedulesView)

    async def test_j_key_scrolls_without_error(self) -> None:
        from github_usage.gui.app import GitHubUsageApp

        tmp, paths = _paths()
        self.addCleanup(tmp.cleanup)
        with mock.patch("github_usage.gui.state.load_setup_paths", return_value=paths):
            app = GitHubUsageApp()

        async with app.run_test(size=(100, 32)) as pilot:
            await pilot.pause(0.05)
            app.action_scroll_down_line()
            self.assertIsNotNone(scroll_target(app))


if __name__ == "__main__":
    unittest.main()
