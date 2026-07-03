"""Tests for TUI layout widgets."""

from __future__ import annotations

import unittest


@unittest.skipUnless(
    __import__("importlib").util.find_spec("textual") is not None,
    "textual not installed",
)
class ViewSectionTests(unittest.IsolatedAsyncioTestCase):
    """ViewSection compose and styling."""

    async def test_view_section_compose(self) -> None:
        from textual.app import App, ComposeResult

        from github_usage.gui.layout import ViewSection

        class PilotApp(App):
            def compose(self) -> ComposeResult:
                yield ViewSection("Test Title", "Test help text")

        async with PilotApp().run_test() as pilot:
            title = pilot.app.query_one(".view-title")
            self.assertIn("Test Title", str(title.render()))
            help_text = pilot.app.query_one(".view-help")
            self.assertIn("Test help text", str(help_text.render()))


if __name__ == "__main__":
    unittest.main()
