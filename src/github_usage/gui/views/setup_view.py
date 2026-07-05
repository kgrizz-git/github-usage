"""Setup and profiles screen for the Textual TUI."""

from __future__ import annotations

from textual import on, work
from textual.app import ComposeResult
from textual.containers import VerticalScroll
from textual.widgets import Button, RichLog, Select, TabbedContent, TabPane

from ...gui_backend import (
    VerifyResult,
    apply_env,
    load_profiles,
    read_secrets,
    save_profiles,
    status_summary,
    update_profile,
    verify_configuration,
    write_secrets,
)
from ..async_ops import AsyncViewMixin
from ..errors import format_error
from ..layout import ViewSection
from ..log_utils import write_log
from ..wizard import SetupWizardScreen
from .setup_profiles_panel import SetupProfilesPanel
from .setup_secrets_panel import SetupSecretsPanel
from .setup_verify_panel import SetupVerifyPanel


class SetupView(VerticalScroll, AsyncViewMixin):
    """Secrets, report options, profiles, verify, and status."""

    DEFAULT_CSS = """
    SetupView {
        height: 1fr;
    }
    #setup-tabs {
        height: 1fr;
    }
    #profiles-empty {
        width: 100%;
        content-align: center middle;
        padding: 2;
    }
    """

    BINDINGS = [
        ("ctrl+s", "save", "Save"),
        ("escape", "cancel_async", "Cancel"),
    ]

    def __init__(self, **kwargs: object) -> None:
        super().__init__(**kwargs)  # type: ignore[arg-type]
        self._is_running = False
        self._cancel_requested = False
        self._dirty = False
        self._loading = True
        self._previous_profile: str | None = None

    def compose(self) -> ComposeResult:
        yield ViewSection(
            "Setup & Report Profiles",
            "Three steps: (1) Secrets — API keys and default email addresses. "
            "(2) Profiles & Options — per-profile email report settings (see on-screen "
            "guide for what applies to Usage Report vs email). Ctrl+S saves. "
            "(3) Verify Email Setup — dry-run for the active profile.",
        )
        yield Button("Start guided setup", id="start-guided-setup", variant="success")
        with TabbedContent(initial="secrets", id="setup-tabs"):
            with TabPane("Secrets", id="secrets"):
                yield SetupSecretsPanel(self, id="secrets-panel")
            with TabPane("Profiles & Options", id="profiles"):
                yield SetupProfilesPanel(self, id="profiles-panel")
            with TabPane("Verify Email Setup", id="verify"):
                yield SetupVerifyPanel(self, id="verify-panel")

    def on_mount(self) -> None:
        state = self.app.app_state  # type: ignore[attr-defined]
        state.add_listener(self._on_state_changed)
        self._on_state_changed()
        if state.config_error:
            self.verify_panel.show_error(state.config_error)

    def on_unmount(self) -> None:
        self.app.app_state.remove_listener(self._on_state_changed)  # type: ignore[attr-defined]

    @property
    def dirty(self) -> bool:
        return self._dirty

    @property
    def is_running(self) -> bool:
        return self._is_running

    def is_form_loading(self) -> bool:
        """Return True while programmatic reload is updating fields."""
        return self._loading

    @property
    def previous_profile(self) -> str | None:
        return self._previous_profile

    @property
    def secrets_panel(self) -> SetupSecretsPanel:
        return self.query_one("#secrets-panel", SetupSecretsPanel)

    @property
    def profiles_panel(self) -> SetupProfilesPanel:
        return self.query_one("#profiles-panel", SetupProfilesPanel)

    @property
    def verify_panel(self) -> SetupVerifyPanel:
        return self.query_one("#verify-panel", SetupVerifyPanel)

    @property
    def verify_log(self) -> RichLog:
        return self.verify_panel.log

    def has_unsaved_changes(self) -> bool:
        return self._dirty

    @on(Button.Pressed, "#start-guided-setup")
    def _start_guided_setup(self) -> None:
        self.app.push_screen(SetupWizardScreen(first_run=False), self._wizard_closed)

    def _wizard_closed(self, completed: bool | None) -> None:
        if completed:
            self.reload_form()
            write_log(self.verify_log, "Guided setup finished", level="success")

    def mark_dirty(self) -> None:
        self._dirty = True
        self.profiles_panel.update_dirty_indicator(True)

    def _on_state_changed(self) -> None:
        self.reload_form()

    def _finish_reload(self) -> None:
        """Clear dirty state after programmatic field updates settle."""
        self._loading = False
        self._clear_dirty_state()
        try:
            self._previous_profile = self.current_profile_name()
        except Exception:
            self._previous_profile = None
        # Deferred Input.Changed events from reload can fire after this pass.
        self.call_after_refresh(self._settle_reload_dirty)

    def _clear_dirty_state(self) -> None:
        self._dirty = False
        self.profiles_panel.update_dirty_indicator(False)

    def _settle_reload_dirty(self) -> None:
        """Drop spurious dirty flags raised by post-reload field events."""
        if not self._loading:
            self._clear_dirty_state()

    def reload_form(self) -> None:
        """Reload form data from config files."""
        self._loading = True
        try:
            state = self.app.app_state  # type: ignore[attr-defined]
            paths = state.paths
            try:
                secrets = read_secrets(paths)
                self.secrets_panel.reload_secrets(secrets)

                names = list(state.profile_names)
                current = state.current_profile
                if current not in names and names:
                    current = names[0]
                    state.set_current_profile(current, notify=False)
                self.profiles_panel.reload_profile_list(names, current)

                if not names:
                    self.profiles_panel.set_empty_state(True)
                    summary = status_summary(paths)
                    status_text = "\n".join(summary["lines"])
                    status_text += f"\nLaunchAgent: {summary['launch_agent']}"
                    self.verify_panel.reload_status(status_text)
                    return

                self.profiles_panel.set_empty_state(False)

                profile_name = self.current_profile_name()
                config = load_profiles(paths)
                try:
                    profile = next(p for p in config["profiles"] if p["name"] == profile_name)
                except StopIteration:
                    profile = config["profiles"][0]
                    select = self.profiles_panel.query_one("#profile-select", Select)
                    select.value = profile["name"]

                self.profiles_panel.reload_profile_options(profile)

                summary = status_summary(paths)
                status_text = "\n".join(summary["lines"])
                status_text += f"\nLaunchAgent: {summary['launch_agent']}"
                self.verify_panel.reload_status(status_text)
            except FileNotFoundError:
                raise
            except PermissionError:
                raise
            except Exception as exc:
                self.verify_panel.show_error(str(exc))
                raise
        finally:
            self.call_after_refresh(self._finish_reload)

    def current_profile_name(self) -> str:
        select = self.profiles_panel.query_one("#profile-select", Select)
        value = select.value
        if value == Select.BLANK or str(value) == "Select.NULL" or value is None:
            return self.app.app_state.current_profile  # type: ignore[attr-defined]
        return str(value)

    def action_save(self) -> None:
        """Persist secrets and the active profile."""
        log = self.verify_log
        paths = self.app.app_state.paths  # type: ignore[attr-defined]
        options = self.profiles_panel.read_profile_options()
        max_repos_str = options["max_repos_str"]

        try:
            max_repos = int(max_repos_str)
            if max_repos < 1:
                write_log(log, "Max repos must be at least 1", level="error")
                return
        except ValueError:
            write_log(
                log,
                f"Invalid max repos value '{max_repos_str}' (must be an integer)",
                level="error",
            )
            return

        try:
            write_log(log, "Saving secrets...", level="progress")
            write_secrets(paths, self.secrets_panel.read_secrets())
            write_log(log, "Secrets saved", level="success")

            write_log(log, "Saving profile configuration...", level="progress")
            config = load_profiles(paths)
            profile = next(
                p for p in config["profiles"] if p["name"] == self.current_profile_name()
            )
            profile["email_report"]["include_forecast"] = options["include_forecast"]
            profile["email_report"]["include_consumers"] = options["include_consumers"]
            profile["email_report"]["include_artifact_storage"] = options[
                "include_artifact_storage"
            ]
            profile["email_report"]["include_release_assets"] = options["include_release_assets"]
            profile["email_report"]["max_repos"] = max_repos
            profile["target_email"] = options["target_email"]
            update_profile(config, profile)
            save_profiles(paths, config)
            apply_env(paths)
            write_log(log, "Profile saved", level="success")

            self._dirty = False
            self.profiles_panel.update_dirty_indicator(False)
            self.app.app_state.reload()  # type: ignore[attr-defined]
            write_log(log, "All changes saved successfully", level="success")
        except (PermissionError, FileNotFoundError, KeyError, ValueError, OSError) as exc:
            write_log(log, format_error(exc, context="Save failed"), level="error")

    def run_verify(self) -> None:
        """Start background verification (triggered from verify panel)."""
        self._run_verify()

    @work(thread=True)
    def _run_verify(self) -> None:
        button = self.verify_panel.query_one("#verify-btn", Button)
        log = self.verify_log
        self._call_ui(
            self._begin_async,
            button,
            log,
            running_label="Verifying...",
            start_message="Starting verification (dry-run)...",
        )

        try:
            if self._is_cancelled():
                self._call_ui(write_log, log, "Verification cancelled", level="warning")
                return
            self._call_ui(write_log, log, "Checking configuration...", level="dim")
            paths = self.app.app_state.paths  # type: ignore[attr-defined]
            result: VerifyResult = verify_configuration(paths, self.current_profile_name())
            if self._is_cancelled():
                self._call_ui(write_log, log, "Verification cancelled", level="warning")
                return
            self._call_ui(self.verify_panel.show_verify_result, result)
        except Exception as exc:
            self._call_ui(
                write_log, log, format_error(exc, context="Verification error"), level="error"
            )
        finally:
            self._call_ui(self._end_async, button, "Verify Email Setup")
