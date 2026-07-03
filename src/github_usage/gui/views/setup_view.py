"""Setup and profiles screen for the Textual TUI."""

from __future__ import annotations

from textual import on, work
from textual.app import ComposeResult
from textual.containers import Horizontal, VerticalScroll
from textual.widgets import Button, Checkbox, Input, Label, RichLog, Select, Static

from ...gui_backend import (
    DEFAULT_PROFILE_NAME,
    VerifyResult,
    add_profile,
    apply_env,
    delete_profile,
    load_profiles,
    load_setup_paths,
    read_secrets,
    save_profiles,
    status_summary,
    update_profile,
    verify_configuration,
    write_secrets,
)


class SetupView(VerticalScroll):
    """Secrets, report options, profiles, verify, and status."""

    DEFAULT_CSS = """
    SetupView {
        height: 1fr;
    }
    """

    BINDINGS = [("ctrl+s", "save", "Save")]

    def compose(self) -> ComposeResult:
        yield Static("Setup & Report Profiles", classes="SectionTitle")
        with Horizontal():
            yield Label("Profile:")
            yield Select([], id="profile-select")
            yield Button("Add", id="add-profile", variant="default")
            yield Button("Delete", id="delete-profile", variant="warning")
        yield Static("Secrets (.env.email-report)", classes="SectionTitle")
        yield Input(placeholder="GITHUB_TOKEN", id="github-token", password=True)
        yield Input(placeholder="RESEND_API_KEY", id="resend-key", password=True)
        yield Input(placeholder="REPORT_EMAIL", id="report-email")
        yield Input(placeholder="RESEND_FROM", id="resend-from")
        yield Static("Report options (config.toml)", classes="SectionTitle")
        yield Checkbox("Include top consumers", id="include-consumers")
        yield Checkbox("Include artifact storage", id="include-artifact")
        yield Checkbox("Include release assets", id="include-release")
        with Horizontal(classes="FormRow"):
            yield Label("Max repos:")
            yield Input(value="100", id="max-repos")
        with Horizontal(classes="FormRow"):
            yield Label("Target email:")
            yield Input(id="target-email")
        with Horizontal():
            yield Button("Save", id="save-btn", variant="primary")
            yield Button("Verify", id="verify-btn", variant="success")
        yield Static("Status", classes="SectionTitle")
        yield Static("", id="status-panel", classes="StatusPanel")
        yield RichLog(id="verify-log", highlight=True, markup=True)

    def on_mount(self) -> None:
        self._paths = load_setup_paths()
        self._reload_form()

    def _profile_names(self) -> list[str]:
        config = load_profiles(self._paths)
        return [p["name"] for p in config.get("profiles", [])]

    def _current_profile_name(self) -> str:
        select = self.query_one("#profile-select", Select)
        value = select.value
        if value == Select.BLANK or str(value) == "Select.NULL" or value is None:
            return DEFAULT_PROFILE_NAME
        return str(value)

    def _reload_form(self) -> None:
        secrets = read_secrets(self._paths)
        self.query_one("#github-token", Input).value = secrets.get("GITHUB_TOKEN", "")
        self.query_one("#resend-key", Input).value = secrets.get("RESEND_API_KEY", "")
        self.query_one("#report-email", Input).value = secrets.get("REPORT_EMAIL", "")
        self.query_one("#resend-from", Input).value = secrets.get("RESEND_FROM", "")

        config = load_profiles(self._paths)
        names = [p["name"] for p in config.get("profiles", [])]
        select = self.query_one("#profile-select", Select)
        select.set_options([(n, n) for n in names])
        current = self._current_profile_name()
        if current in names:
            select.value = current
        profile = next(p for p in config["profiles"] if p["name"] == self._current_profile_name())
        email = profile["email_report"]
        self.query_one("#include-consumers", Checkbox).value = bool(email.get("include_consumers"))
        self.query_one("#include-artifact", Checkbox).value = bool(
            email.get("include_artifact_storage")
        )
        self.query_one("#include-release", Checkbox).value = bool(
            email.get("include_release_assets")
        )
        self.query_one("#max-repos", Input).value = str(email.get("max_repos", 100))
        self.query_one("#target-email", Input).value = profile.get("target_email", "")

        summary = status_summary(self._paths)
        status_text = "\n".join(summary["lines"])
        status_text += f"\nLaunchAgent: {summary['launch_agent']}"
        self.query_one("#status-panel", Static).update(status_text)

    @on(Select.Changed, "#profile-select")
    def _on_profile_changed(self) -> None:
        self._reload_form()

    @on(Button.Pressed, "#save-btn")
    def _save_pressed(self) -> None:
        self.action_save()

    def action_save(self) -> None:
        """Persist secrets and the active profile."""
        log = self.query_one("#verify-log", RichLog)
        try:
            write_secrets(
                self._paths,
                {
                    "GITHUB_TOKEN": self.query_one("#github-token", Input).value.strip(),
                    "RESEND_API_KEY": self.query_one("#resend-key", Input).value.strip(),
                    "REPORT_EMAIL": self.query_one("#report-email", Input).value.strip(),
                    "RESEND_FROM": self.query_one("#resend-from", Input).value.strip(),
                },
            )
            config = load_profiles(self._paths)
            profile = next(
                p for p in config["profiles"] if p["name"] == self._current_profile_name()
            )
            profile["email_report"]["include_consumers"] = self.query_one(
                "#include-consumers", Checkbox
            ).value
            profile["email_report"]["include_artifact_storage"] = self.query_one(
                "#include-artifact", Checkbox
            ).value
            profile["email_report"]["include_release_assets"] = self.query_one(
                "#include-release", Checkbox
            ).value
            profile["email_report"]["max_repos"] = int(
                self.query_one("#max-repos", Input).value.strip() or "100"
            )
            profile["target_email"] = self.query_one("#target-email", Input).value.strip()
            update_profile(config, profile)
            save_profiles(self._paths, config)
            apply_env(self._paths)
            log.write("[green]Saved secrets and profile.[/green]")
            self._reload_form()
        except (ValueError, KeyError, OSError) as exc:
            log.write(f"[red]Save failed: {exc}[/red]")

    @on(Button.Pressed, "#verify-btn")
    def _verify_pressed(self) -> None:
        self._run_verify()

    @work(thread=True)
    def _run_verify(self) -> None:
        log = self.query_one("#verify-log", RichLog)
        log.write("Running email-report --dry-run…")
        result: VerifyResult = verify_configuration(self._paths, self._current_profile_name())
        self.call_from_thread(self._show_verify_result, result)

    def _show_verify_result(self, result: VerifyResult) -> None:
        log = self.query_one("#verify-log", RichLog)
        if result.output.strip():
            log.write(result.output.rstrip())
        if result.exit_code == 0:
            log.write("[green]Verification passed.[/green]")
        else:
            log.write("[red]Verification failed.[/red]")

    @on(Button.Pressed, "#add-profile")
    def _add_profile(self) -> None:
        config = load_profiles(self._paths)
        name = f"profile{len(config.get('profiles', [])) + 1}"
        try:
            config = add_profile(config, name)
            save_profiles(self._paths, config)
            self._reload_form()
        except ValueError as exc:
            self.query_one("#verify-log", RichLog).write(f"[red]{exc}[/red]")

    @on(Button.Pressed, "#delete-profile")
    def _delete_profile(self) -> None:
        log = self.query_one("#verify-log", RichLog)
        try:
            config = load_profiles(self._paths)
            config = delete_profile(config, self._current_profile_name())
            save_profiles(self._paths, config)
            self._reload_form()
            log.write("[yellow]Profile deleted.[/yellow]")
        except (ValueError, KeyError) as exc:
            log.write(f"[red]{exc}[/red]")
