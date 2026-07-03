"""Tests for TUI shared helpers (errors, prefs, state)."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from github_usage.gui.async_ops import AsyncViewMixin
from github_usage.gui.errors import format_error, format_simple
from github_usage.gui.prefs import GuiPreferences, load_gui_prefs, save_gui_prefs
from github_usage.gui.state import AppState
from github_usage.gui_backend import load_setup_paths, write_secrets


class AsyncViewMixinTests(unittest.TestCase):
    """Thread marshaling for @work background tasks."""

    def test_call_ui_delegates_to_app(self) -> None:
        class Host(AsyncViewMixin):
            def __init__(self, app: object) -> None:
                self.app = app

        app = mock.MagicMock()
        host = Host(app)
        host._call_ui(lambda: None, 1, key="x")
        app.call_from_thread.assert_called_once()


class FormatErrorTests(unittest.TestCase):
    """Actionable error message formatting."""

    def test_file_not_found_hint(self) -> None:
        text = format_error(FileNotFoundError("missing"))
        self.assertIn("Config missing", text)

    def test_permission_error_hint(self) -> None:
        text = format_error(PermissionError("denied"))
        self.assertIn("file permissions", text.lower())

    def test_key_error_hint(self) -> None:
        text = format_error(KeyError("team"))
        self.assertIn("Profile not found", text)

    def test_format_simple_includes_message(self) -> None:
        text = format_simple("Something broke", hint="Try again")
        self.assertIn("Something broke", text)
        self.assertIn("Try again", text)


class GuiPrefsTests(unittest.TestCase):
    """GUI preference persistence."""

    def test_round_trip_prefs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            paths = load_setup_paths(Path(tmp))
            prefs = GuiPreferences(
                last_view="report",
                last_profile="team",
                report_timeout=45.0,
                report_max_retries=5,
            )
            save_gui_prefs(paths, prefs)
            loaded = load_gui_prefs(paths)
            self.assertEqual(loaded.last_view, "report")
            self.assertEqual(loaded.last_profile, "team")
            self.assertEqual(loaded.report_timeout, 45.0)
            self.assertEqual(loaded.report_max_retries, 5)


class AppStateTests(unittest.TestCase):
    """Centralized AppState reload and profile tracking."""

    def test_reload_reads_profiles(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = load_setup_paths(root)
            write_secrets(
                paths,
                {
                    "GITHUB_TOKEN": "ghp_test",
                    "RESEND_API_KEY": "re_test",
                    "REPORT_EMAIL": "user@example.com",
                    "RESEND_FROM": "from@example.com",
                },
            )
            state = AppState(paths=paths)
            state.reload()
            self.assertIn("default", state.profile_names)
            self.assertEqual(state.current_profile, "default")

    def test_set_current_profile_persists(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            paths = load_setup_paths(Path(tmp))
            state = AppState(paths=paths)
            state.reload()
            state.set_current_profile("default")
            reloaded = load_gui_prefs(paths)
            self.assertEqual(reloaded.last_profile, "default")


if __name__ == "__main__":
    unittest.main()
