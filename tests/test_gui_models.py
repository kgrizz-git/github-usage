"""Tests for TUI routing and gui_backend setup helpers."""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from github_usage.cli_gui import _MISSING_GUI_MESSAGE, route_entry
from github_usage.gui_backend import (
    DEFAULT_PROFILE_NAME,
    add_profile,
    delete_profile,
    load_profiles,
    load_setup_paths,
    read_secrets,
    save_profiles,
    write_secrets,
)


class RouteEntryTests(unittest.TestCase):
    """Top-level argv routing before CLI subcommand dispatch."""

    def test_explicit_cli_empty_shows_help(self) -> None:
        with mock.patch("github_usage.cli_gui.print") as printed:
            result = route_entry(["--cli"])
        self.assertTrue(result.handled)
        self.assertEqual(result.exit_code, 0)
        printed.assert_called_once()

    def test_subcommand_shortcut_skips_tui(self) -> None:
        result = route_entry(["setup", "--status"])
        self.assertFalse(result.handled)
        self.assertEqual(result.argv, ["setup", "--status"])

    def test_env_cli_mode_routes_to_legacy(self) -> None:
        with mock.patch.dict(os.environ, {"GITHUB_USAGE_CLI": "1"}):
            result = route_entry([])
        self.assertFalse(result.handled)
        self.assertEqual(result.argv, [])

    def test_non_tty_empty_prints_help(self) -> None:
        with (
            mock.patch("sys.stdin.isatty", return_value=False),
            mock.patch("sys.stdout.isatty", return_value=False),
            mock.patch("github_usage.cli_gui.print") as printed,
        ):
            result = route_entry([])
        self.assertTrue(result.handled)
        self.assertEqual(result.exit_code, 0)
        printed.assert_called_once()

    def test_tty_default_launches_tui(self) -> None:
        with (
            mock.patch("github_usage.cli_gui.run_tui", return_value=0) as run_tui,
            mock.patch("sys.stdin.isatty", return_value=True),
            mock.patch("sys.stdout.isatty", return_value=True),
        ):
            result = route_entry([])
        self.assertTrue(result.handled)
        self.assertEqual(result.exit_code, 0)
        run_tui.assert_called_once()

    def test_missing_gui_message_contains_venv_python(self) -> None:
        self.assertIn("uv pip install --python .venv -e '.[gui]'", _MISSING_GUI_MESSAGE)


@unittest.skipUnless(
    __import__("importlib").util.find_spec("textual") is not None,
    "textual not installed",
)
class SetupViewPilotTests(unittest.IsolatedAsyncioTestCase):
    """Headless Textual pilot smoke for the setup screen."""

    async def test_setup_view_mounts(self) -> None:
        from textual.app import App, ComposeResult

        from github_usage.gui.views.setup_view import SetupView

        class PilotApp(App):
            def compose(self) -> ComposeResult:
                yield SetupView()

        async with PilotApp().run_test() as pilot:
            self.assertIsNotNone(pilot.app)


class GuiBackendProfileTests(unittest.TestCase):
    """Profile and secrets persistence via gui_backend."""

    def test_default_profile_name_export(self) -> None:
        self.assertEqual(DEFAULT_PROFILE_NAME, "default")

    def test_write_and_read_secrets(self) -> None:
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
            secrets = read_secrets(paths)
            self.assertEqual(secrets["REPORT_EMAIL"], "user@example.com")

    def test_add_and_delete_profile(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = load_setup_paths(root)
            config = load_profiles(paths)
            config = add_profile(config, "team")
            save_profiles(paths, config)
            config = load_profiles(paths)
            self.assertEqual(len(config["profiles"]), 2)
            config = delete_profile(config, "team")
            save_profiles(paths, config)
            config = load_profiles(paths)
            self.assertEqual(len(config["profiles"]), 1)


if __name__ == "__main__":
    unittest.main()
