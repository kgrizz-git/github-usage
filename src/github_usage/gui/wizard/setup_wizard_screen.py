"""Guided setup wizard modal for the Textual TUI."""

from __future__ import annotations

import sys

from textual import on, work
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Checkbox, ContentSwitcher, Input, Label, RichLog, Static

from ..errors import format_error
from ..layout import FormGrid
from ..log_utils import write_log
from ..views.setup_secrets_panel import SECRET_FIELDS
from ..widgets.schedule_picker import SchedulePicker
from .setup_wizard_flow import (
    STEP_TITLES,
    WizardData,
    install_launch_agent,
    load_initial_data,
    review_summary,
    run_verify,
    save_ga_schedule_step,
    save_local_schedule_step,
    save_options_step,
    save_secrets_step,
    validate_options,
    validate_secrets,
)


class SetupWizardScreen(ModalScreen[bool]):
    """Multi-step first-run and guided setup. Dismisses True when completed."""

    DEFAULT_CSS = """
    SetupWizardScreen {
        align: center middle;
    }
    #wizard-dialog {
        width: 72;
        height: auto;
        max-height: 90%;
        border: thick $primary;
        background: $surface;
        padding: 1 2;
    }
    #wizard-progress {
        color: $text-muted;
        margin-bottom: 1;
    }
    #wizard-steps {
        height: auto;
        min-height: 8;
        margin-bottom: 1;
    }
    #wizard-buttons {
        height: auto;
        align: center middle;
    }
    #wizard-buttons Button {
        margin: 0 1;
    }
    #wizard-verify-log {
        height: 10;
        border: solid $primary;
    }
    """

    def __init__(self, *, first_run: bool = False) -> None:
        super().__init__()
        self._step = 0
        self._first_run = first_run
        self._data = WizardData()
        self._verifying = False

    def compose(self) -> ComposeResult:
        with Vertical(id="wizard-dialog"):
            yield Static("", id="wizard-progress")
            with ContentSwitcher(initial="step-welcome", id="wizard-steps"):
                yield Static(
                    "Welcome to github-usage setup.\n\n"
                    "This guided flow configures the [b]default[/b] report profile in "
                    "about five minutes. You will need:\n"
                    "· GitHub personal access token (billing read)\n"
                    "· Resend API key and verified sender domain\n"
                    "· Recipient email address\n\n"
                    "Schedules use plain day/time pickers — no cron knowledge required.",
                    id="step-welcome",
                )
                with Vertical(id="step-secrets"):
                    yield Static("Paste secrets (.env.email-report)", classes="SectionTitle")
                    yield Checkbox("Show hidden values", id="wizard-show-secrets")
                    for field_id, env_key, description, hidden in SECRET_FIELDS:
                        with FormGrid():
                            yield Label(env_key, classes="field-key")
                            yield Static(description, classes="field-help")
                        yield Input(id=f"wizard-{field_id}", password=hidden)
                with Vertical(id="step-options"):
                    yield Static("Email report options", classes="SectionTitle")
                    yield Checkbox("Include forecast", id="wizard-forecast", value=True)
                    yield Checkbox("Include top consumers", id="wizard-consumers")
                    yield Checkbox("Include artifact storage", id="wizard-artifact")
                    yield Checkbox("Include release assets", id="wizard-release")
                    with FormGrid():
                        yield Label("Max repos:")
                        yield Input(value="100", id="wizard-max-repos")
                        yield Label("target_email:")
                        yield Input(
                            placeholder="Optional — uses REPORT_EMAIL when blank",
                            id="wizard-target-email",
                        )
                yield SchedulePicker(
                    id="wizard-local-picker",
                    show_local=True,
                    show_ga=False,
                )
                with Vertical(id="step-ga"):
                    yield SchedulePicker(
                        id="wizard-ga-picker",
                        show_local=False,
                        show_ga=True,
                    )
                yield Static("", id="step-review")
                with Vertical(id="step-verify"):
                    yield Static(
                        "Dry-run email report for the default profile.",
                        classes="HelpText",
                    )
                    yield RichLog(id="wizard-verify-log", highlight=True, markup=True)
                with Vertical(id="step-finish"):
                    yield Static("Setup complete", classes="SectionTitle")
                    yield Static("", id="wizard-finish-message")
                    if sys.platform == "darwin":
                        yield Checkbox(
                            "Install macOS LaunchAgent for local schedule",
                            id="wizard-install-la",
                            value=True,
                        )
                    else:
                        yield Static(
                            "Local launchd is macOS-only. GitHub Actions schedule is configured.",
                            classes="HelpText",
                        )
                    yield Static(
                        "CI secrets (`gh secret set`) and dev hooks: run "
                        "`./start.sh setup` in a terminal for those steps.",
                        classes="HelpText",
                    )
            with Horizontal(id="wizard-buttons"):
                yield Button("Cancel", id="wizard-cancel")
                yield Button("Back", id="wizard-back", disabled=True)
                if self._first_run:
                    yield Button("Skip for now", id="wizard-skip", variant="warning")
                yield Button("Next", id="wizard-next", variant="primary")

    def on_mount(self) -> None:
        paths = self.app.app_state.paths  # type: ignore[attr-defined]
        self._data = load_initial_data(paths)
        self._populate_secrets()
        self._populate_options()
        local_picker = self.query_one("#wizard-local-picker", SchedulePicker)
        local_picker.set_local_schedule(
            self._data.local_weekday,
            self._data.local_hour,
            self._data.local_minute,
        )
        ga_picker = self.query_one("#wizard-ga-picker", SchedulePicker)
        ga_picker.set_ga_cron(self._data.ga_cron)
        self._update_progress()

    def _populate_secrets(self) -> None:
        for field_id, env_key, _, _ in SECRET_FIELDS:
            self.query_one(f"#wizard-{field_id}", Input).value = self._data.secrets.get(env_key, "")

    def _populate_options(self) -> None:
        self.query_one("#wizard-forecast", Checkbox).value = self._data.include_forecast
        self.query_one("#wizard-consumers", Checkbox).value = self._data.include_consumers
        self.query_one("#wizard-artifact", Checkbox).value = self._data.include_artifact_storage
        self.query_one("#wizard-release", Checkbox).value = self._data.include_release_assets
        self.query_one("#wizard-max-repos", Input).value = str(self._data.max_repos)
        self.query_one("#wizard-target-email", Input).value = self._data.target_email

    def _read_secrets_from_form(self) -> None:
        self._data.secrets = {
            env_key: self.query_one(f"#wizard-{field_id}", Input).value.strip()
            for field_id, env_key, _, _ in SECRET_FIELDS
        }

    def _read_options_from_form(self) -> None:
        try:
            max_repos = int(self.query_one("#wizard-max-repos", Input).value.strip() or "100")
        except ValueError:
            max_repos = 0
        self._data.max_repos = max_repos
        self._data.include_forecast = self.query_one("#wizard-forecast", Checkbox).value
        self._data.include_consumers = self.query_one("#wizard-consumers", Checkbox).value
        self._data.include_artifact_storage = self.query_one("#wizard-artifact", Checkbox).value
        self._data.include_release_assets = self.query_one("#wizard-release", Checkbox).value
        self._data.target_email = self.query_one("#wizard-target-email", Input).value.strip()

    def _read_local_from_form(self) -> bool:
        local = self.query_one("#wizard-local-picker", SchedulePicker).get_local_schedule()
        if local is None:
            return False
        self._data.local_weekday = local.weekday
        self._data.local_hour = local.hour
        self._data.local_minute = local.minute
        return True

    def _read_ga_from_form(self) -> bool:
        cron = self.query_one("#wizard-ga-picker", SchedulePicker).get_ga_cron()
        if cron is None:
            return False
        self._data.ga_cron = cron
        return True

    def _step_id(self, index: int) -> str:
        ids = (
            "step-welcome",
            "step-secrets",
            "step-options",
            "wizard-local-picker",
            "step-ga",
            "step-review",
            "step-verify",
            "step-finish",
        )
        return ids[index]

    def _update_progress(self) -> None:
        total = len(STEP_TITLES)
        title = STEP_TITLES[self._step]
        self.query_one("#wizard-progress", Static).update(
            f"Step {self._step + 1} of {total}: [b]{title}[/b]"
        )
        switcher = self.query_one("#wizard-steps", ContentSwitcher)
        switcher.current = self._step_id(self._step)
        self.query_one("#wizard-back", Button).disabled = self._step == 0
        next_btn = self.query_one("#wizard-next", Button)
        if self._step == len(STEP_TITLES) - 1:
            next_btn.label = "Done"
        elif self._step == len(STEP_TITLES) - 2:
            next_btn.label = "Continue"
        else:
            next_btn.label = "Next"

    @on(Checkbox.Changed, "#wizard-show-secrets")
    def _toggle_wizard_secrets(self, event: Checkbox.Changed) -> None:
        visible = bool(event.value)
        for field_id, _, _, hidden in SECRET_FIELDS:
            if hidden:
                self.query_one(f"#wizard-{field_id}", Input).password = not visible

    @on(Button.Pressed, "#wizard-cancel")
    def _cancel_wizard(self) -> None:
        self.dismiss(False)

    @on(Button.Pressed, "#wizard-skip")
    def _skip_wizard(self) -> None:
        self.app.app_state.dismiss_setup_wizard()  # type: ignore[attr-defined]
        self.dismiss(False)

    @on(Button.Pressed, "#wizard-back")
    def _back(self) -> None:
        if self._step > 0:
            self._step -= 1
            self._update_progress()

    @on(Button.Pressed, "#wizard-next")
    def _next(self) -> None:
        if self._step == len(STEP_TITLES) - 1:
            self._finish()
            return
        if self._step > 0:
            error = self._validate_and_save_current_step()
            if error:
                return
        self._step += 1
        if self._step == 5:
            self.query_one("#step-review", Static).update(review_summary(self._data))
        if self._step == 6:
            self._start_verify()
        if self._step == 7:
            self.query_one("#wizard-finish-message", Static).update(
                "Configuration saved. Optional: install the LaunchAgent below."
            )
        self._update_progress()

    def _validate_and_save_current_step(self) -> str | None:
        paths = self.app.app_state.paths  # type: ignore[attr-defined]
        log = self.query_one("#wizard-verify-log", RichLog)

        if self._step == 1:
            self._read_secrets_from_form()
            error = validate_secrets(self._data)
            if error:
                write_log(log, error, level="error")
                return error
            try:
                save_secrets_step(paths, self._data)
            except (PermissionError, OSError) as exc:
                write_log(log, format_error(exc), level="error")
                return str(exc)
        elif self._step == 2:
            self._read_options_from_form()
            error = validate_options(self._data)
            if error:
                write_log(log, error, level="error")
                return error
            try:
                save_options_step(paths, self._data)
            except (PermissionError, OSError, KeyError, ValueError) as exc:
                write_log(log, format_error(exc), level="error")
                return str(exc)
        elif self._step == 3:
            picker = self.query_one("#wizard-local-picker", SchedulePicker)
            error = picker.validate()
            if error:
                write_log(log, error, level="error")
                return error
            if not self._read_local_from_form():
                return "Invalid local schedule"
            try:
                save_local_schedule_step(paths, self._data)
            except (PermissionError, OSError, ValueError, KeyError) as exc:
                write_log(log, format_error(exc), level="error")
                return str(exc)
        elif self._step == 4:
            picker = self.query_one("#wizard-ga-picker", SchedulePicker)
            error = picker.validate()
            if error:
                write_log(log, error, level="error")
                return error
            if not self._read_ga_from_form():
                return "Invalid GitHub Actions schedule"
            try:
                save_ga_schedule_step(paths, self._data)
            except (PermissionError, OSError, ValueError, KeyError) as exc:
                write_log(log, format_error(exc), level="error")
                return str(exc)
        return None

    def _start_verify(self) -> None:
        if self._verifying:
            return
        self._verifying = True
        log = self.query_one("#wizard-verify-log", RichLog)
        log.clear()
        write_log(log, "Running email-report dry-run...", level="progress")
        self._run_verify_worker()

    @work(thread=True)
    def _run_verify_worker(self) -> None:
        paths = self.app.app_state.paths  # type: ignore[attr-defined]
        try:
            result = run_verify(paths)
            self._data.verify_result = result

            def _report() -> None:
                log = self.query_one("#wizard-verify-log", RichLog)
                if result.exit_code == 0:
                    write_log(log, "Verify passed", level="success")
                else:
                    write_log(log, result.output or "Verify failed", level="error")

            self.app.call_from_thread(_report)
        except Exception as exc:
            err = exc

            def _report_error() -> None:
                write_log(
                    self.query_one("#wizard-verify-log", RichLog),
                    format_error(err, context="Verify failed"),
                    level="error",
                )

            self.app.call_from_thread(_report_error)
        finally:
            self._verifying = False

    def _finish(self) -> None:
        paths = self.app.app_state.paths  # type: ignore[attr-defined]
        log = self.query_one("#wizard-verify-log", RichLog)
        if sys.platform == "darwin":
            install_box = self.query_one("#wizard-install-la", Checkbox)
            if install_box.value:
                try:
                    code, message = install_launch_agent(paths)
                    write_log(log, message or f"LaunchAgent exit {code}", level="info")
                except Exception as exc:
                    write_log(log, format_error(exc), level="error")
        self.app.app_state.reload()  # type: ignore[attr-defined]
        self.app.app_state.set_wizard_completed(True)  # type: ignore[attr-defined]
        self.dismiss(True)
