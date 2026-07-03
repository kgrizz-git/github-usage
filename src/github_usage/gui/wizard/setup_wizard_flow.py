"""Guided setup wizard state and persistence for the Textual TUI."""

from __future__ import annotations

import sys
from dataclasses import dataclass, field

from ...gui_backend import (
    VerifyResult,
    apply_env,
    configure_github_actions_fields,
    configure_schedule_fields,
    install_launch_agent_for_paths,
    load_profiles,
    read_secrets,
    regenerate_launchd_plist,
    regenerate_workflow_file,
    save_profiles,
    update_profile,
    verify_configuration,
    write_secrets,
)
from ...schedule_helpers import describe_cron_human, describe_local_schedule
from ...setup_config import SetupPaths
from ...setup_workflow import DEFAULT_PROFILE_NAME

STEP_TITLES: tuple[str, ...] = (
    "Welcome",
    "Secrets",
    "Report options",
    "Local schedule",
    "Cloud schedule",
    "Review",
    "Verify",
    "Finish",
)


@dataclass
class WizardData:
    """Collected wizard answers (default profile only)."""

    secrets: dict[str, str] = field(default_factory=dict)
    include_consumers: bool = False
    include_artifact_storage: bool = False
    include_release_assets: bool = False
    max_repos: int = 100
    target_email: str = ""
    local_weekday: int = 1
    local_hour: int = 9
    local_minute: int = 0
    ga_cron: str = "0 9 * * 1"
    verify_result: VerifyResult | None = None


def load_initial_data(paths: SetupPaths) -> WizardData:
    """Seed wizard fields from disk when present."""
    data = WizardData()
    try:
        data.secrets = read_secrets(paths)
    except (FileNotFoundError, PermissionError):
        data.secrets = {}
    if not paths.config_file.is_file():
        return data
    config = load_profiles(paths)
    profiles = config.get("profiles") or []
    if not profiles:
        return data
    profile = next((p for p in profiles if p["name"] == DEFAULT_PROFILE_NAME), profiles[0])
    email = profile.get("email_report", {})
    data.include_consumers = bool(email.get("include_consumers"))
    data.include_artifact_storage = bool(email.get("include_artifact_storage"))
    data.include_release_assets = bool(email.get("include_release_assets"))
    data.max_repos = int(email.get("max_repos", 100))
    data.target_email = profile.get("target_email", "")
    sched = profile.get("schedule", {})
    data.local_weekday = int(sched.get("weekday", 1))
    data.local_hour = int(sched.get("hour", 9))
    data.local_minute = int(sched.get("minute", 0))
    ga = profile.get("github_actions", {})
    data.ga_cron = str(ga.get("cron", "0 9 * * 1"))
    return data


def validate_secrets(data: WizardData) -> str | None:
    """Return an error when required secrets are missing."""
    missing = [
        key
        for key in ("GITHUB_TOKEN", "RESEND_API_KEY", "REPORT_EMAIL", "RESEND_FROM")
        if not data.secrets.get(key, "").strip()
    ]
    if missing:
        return f"Required: {', '.join(missing)}"
    return None


def validate_options(data: WizardData) -> str | None:
    """Return an error message when report option fields are invalid."""
    if data.max_repos < 1:
        return "Max repos must be at least 1"
    return None


def save_secrets_step(paths: SetupPaths, data: WizardData) -> None:
    """Persist wizard secrets and apply them to the process environment."""
    write_secrets(paths, data.secrets)
    apply_env(paths)


def save_options_step(paths: SetupPaths, data: WizardData) -> None:
    """Save email-report options on the default profile."""
    config = load_profiles(paths)
    profile = next(
        (p for p in config["profiles"] if p["name"] == DEFAULT_PROFILE_NAME),
        config["profiles"][0],
    )
    email = profile.setdefault("email_report", {})
    email["include_consumers"] = data.include_consumers
    email["include_artifact_storage"] = data.include_artifact_storage
    email["include_release_assets"] = data.include_release_assets
    email["max_repos"] = data.max_repos
    profile["target_email"] = data.target_email
    update_profile(config, profile)
    save_profiles(paths, config)
    apply_env(paths)


def save_local_schedule_step(paths: SetupPaths, data: WizardData) -> None:
    """Persist the local launchd schedule for the default profile."""
    configure_schedule_fields(
        paths,
        DEFAULT_PROFILE_NAME,
        weekday=data.local_weekday,
        hour=data.local_hour,
        minute=data.local_minute,
    )


def save_ga_schedule_step(paths: SetupPaths, data: WizardData) -> None:
    """Persist GitHub Actions cron and regenerate workflow/plist artifacts."""
    ga = load_profiles(paths)
    profile = next(p for p in ga["profiles"] if p["name"] == DEFAULT_PROFILE_NAME)
    existing_ga = profile.get("github_actions", {})
    configure_github_actions_fields(
        paths,
        DEFAULT_PROFILE_NAME,
        cron=data.ga_cron,
        include_consumers=bool(existing_ga.get("include_consumers", data.include_consumers)),
        include_artifact_storage=bool(
            existing_ga.get("include_artifact_storage", data.include_artifact_storage)
        ),
        include_release_assets=bool(
            existing_ga.get("include_release_assets", data.include_release_assets)
        ),
    )
    regenerate_workflow_file(paths, DEFAULT_PROFILE_NAME)
    if sys.platform == "darwin":
        regenerate_launchd_plist(paths, DEFAULT_PROFILE_NAME)


def run_verify(paths: SetupPaths) -> VerifyResult:
    """Run configuration verification for the default profile."""
    return verify_configuration(paths, DEFAULT_PROFILE_NAME)


def install_launch_agent(paths: SetupPaths) -> tuple[int, str]:
    """Install the macOS LaunchAgent for the default profile."""
    return install_launch_agent_for_paths(paths)


def review_summary(data: WizardData) -> str:
    """Plain-language summary without secret values."""
    recipient = data.target_email or data.secrets.get("REPORT_EMAIL", "(not set)")
    lines = [
        "[b]Secrets[/b]: GitHub token, Resend key, and email addresses configured",
        f"[b]Recipient[/b]: {recipient}",
        f"[b]Report sections[/b]: consumers={data.include_consumers}, "
        f"artifacts={data.include_artifact_storage}, releases={data.include_release_assets}",
        f"[b]Max repos[/b]: {data.max_repos}",
        f"[b]Local schedule[/b]: "
        f"{describe_local_schedule(data.local_weekday, data.local_hour, data.local_minute)}",
    ]
    ga_human = describe_cron_human(data.ga_cron) or data.ga_cron
    lines.append(f"[b]GitHub Actions[/b]: {ga_human}")
    if sys.platform != "darwin":
        lines.append("[b]LaunchAgent[/b]: macOS only — use GitHub Actions on this platform")
    return "\n".join(lines)
