"""Integration tests for the production Textual app entry path."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from github_usage.gui_backend import load_profiles, load_setup_paths, save_profiles, write_secrets


def _temp_paths() -> tuple[tempfile.TemporaryDirectory[str], object]:
    """Return isolated setup paths with secrets and default profile config."""
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


def _make_app(paths: object) -> object:
    """Create a GitHubUsageApp wired to isolated temp paths.

    ``mock.patch("github_usage.gui.state.load_setup_paths")`` does not
    propagate into ``AppState`` because the dataclass ``default_factory``
    captures a direct reference to the original function object at class
    definition time — patching the module attribute has no effect on the
    already-captured reference.  The correct isolation strategy is to
    construct ``AppState(paths=paths)`` explicitly and assign it to the
    app before ``run_test`` begins.
    """
    from github_usage.gui.app import GitHubUsageApp
    from github_usage.gui.state import AppState

    app = GitHubUsageApp()
    app.app_state = AppState(paths=paths)  # type: ignore[arg-type]
    return app


@unittest.skipUnless(
    __import__("importlib").util.find_spec("textual") is not None,
    "textual not installed",
)
class GitHubUsageAppIntegrationTests(unittest.IsolatedAsyncioTestCase):
    """Exercise GitHubUsageApp with isolated config (production entry class)."""

    async def test_app_mounts_clean_and_switches_tabs(self) -> None:
        from textual.widgets import TabbedContent

        from github_usage.gui.main_window import MainWindow
        from github_usage.gui.views.setup_view import SetupView

        tmp, paths = _temp_paths()
        self.addCleanup(tmp.cleanup)
        app = _make_app(paths)

        async with app.run_test(size=(100, 32)) as pilot:  # type: ignore[union-attr]
            await pilot.pause(0.05)
            setup = pilot.app.query_one(SetupView)
            main = pilot.app.query_one(MainWindow)
            tabs = main.query_one("#main-tabs", TabbedContent)

            self.assertFalse(
                setup.has_unsaved_changes(),
                "setup should not block navigation after reload settles",
            )
            self.assertEqual(tabs.active, "setup")

            main.action_show_view("report")
            self.assertEqual(tabs.active, "report")
            self.assertEqual(main._active_view_id, "report")

            await pilot.click("#--content-tab-email")
            self.assertEqual(tabs.active, "email")

    async def test_guided_setup_button_opens_wizard(self) -> None:
        from github_usage.gui.wizard import SetupWizardScreen

        tmp, paths = _temp_paths()
        self.addCleanup(tmp.cleanup)
        app = _make_app(paths)

        async with app.run_test(size=(100, 40)) as pilot:  # type: ignore[union-attr]
            await pilot.pause(0.05)
            await pilot.click("#start-guided-setup")
            await pilot.pause(0.05)
            wizard = pilot.app.screen
            self.assertIsInstance(wizard, SetupWizardScreen)
            await pilot.click("#wizard-cancel")

    async def test_setup_secrets_show_hide_toggle(self) -> None:
        from textual.widgets import Checkbox, Input, TabbedContent

        from github_usage.gui.main_window import MainWindow
        from github_usage.gui.views.setup_secrets_panel import SetupSecretsPanel

        tmp, paths = _temp_paths()
        self.addCleanup(tmp.cleanup)
        app = _make_app(paths)

        async with app.run_test(size=(100, 32)) as pilot:  # type: ignore[union-attr]
            await pilot.pause(0.05)
            panel = pilot.app.query_one(SetupSecretsPanel)
            token = panel.query_one("#github-token", Input)
            self.assertTrue(token.password)
            await pilot.click("#show-secrets")
            self.assertFalse(token.password)
            show = panel.query_one("#show-secrets", Checkbox)
            self.assertTrue(show.value)

        tmp2, paths2 = _temp_paths()
        self.addCleanup(tmp2.cleanup)
        app2 = _make_app(paths2)

        async with app2.run_test(size=(100, 32)) as pilot:  # type: ignore[union-attr]
            await pilot.pause(0.05)
            tabs = pilot.app.query_one(MainWindow).query_one("#main-tabs", TabbedContent)
            await pilot.press("2")
            self.assertEqual(tabs.active, "report")


class AppStateNotifyTests(unittest.TestCase):
    """AppState listener behavior used during form reload."""

    def test_set_current_profile_can_skip_notify(self) -> None:
        from github_usage.gui.state import AppState

        tmp, paths = _temp_paths()
        self.addCleanup(tmp.cleanup)
        state = AppState(paths=paths)  # type: ignore[arg-type]
        state.reload()
        calls = 0

        def listener() -> None:
            nonlocal calls
            calls += 1

        state.add_listener(listener)
        state.current_profile = "other"
        state.set_current_profile("default", notify=True)
        self.assertEqual(calls, 1)
        state.set_current_profile("default", notify=True)
        self.assertEqual(calls, 1, "unchanged profile should not notify again")


if __name__ == "__main__":
    unittest.main()
