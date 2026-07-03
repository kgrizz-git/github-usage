"""Pilot tests for TUI tab navigation."""

from __future__ import annotations

import unittest


@unittest.skipUnless(
    __import__("importlib").util.find_spec("textual") is not None,
    "textual not installed",
)
class MainWindowNavigationTests(unittest.IsolatedAsyncioTestCase):
    async def test_tab_switch_is_immediate_without_unsaved_changes(self) -> None:
        from textual.app import App, ComposeResult
        from textual.widgets import TabbedContent

        from github_usage.gui.main_window import MainWindow
        from github_usage.gui.state import AppState

        class PilotApp(App):
            def __init__(self) -> None:
                super().__init__()
                self.app_state = AppState()

            def compose(self) -> ComposeResult:
                yield MainWindow()

        async with PilotApp().run_test() as pilot:
            main = pilot.app.query_one(MainWindow)
            tabs = main.query_one("#main-tabs", TabbedContent)
            self.assertEqual(tabs.active, "setup")
            await pilot.click("#--content-tab-report")
            self.assertEqual(tabs.active, "report")
