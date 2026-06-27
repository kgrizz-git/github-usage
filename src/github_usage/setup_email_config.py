"""Email-report option prompting for the setup wizard.

Lifted out of ``setup_wizard`` so the wizard file stays focused on
orchestration. Configures which sections appear in the email and the
max repositories to scan, stored in ``.github-usage/config.toml``.
"""

from __future__ import annotations

from .setup_config import SetupPaths, _load_or_create_config, find_profile, write_config
from .setup_prompts import _prompt_int, _prompt_yes_no


def _prompt_email_format(default: str) -> str:
    """Prompt for --email-format value, re-prompting on invalid input."""
    while True:
        raw = input(f"  Email body format (text | html)? [{default}]: ").strip()
        choice = (raw or default).lower()
        if choice in ("text", "html"):
            return choice
        print(f"  Invalid choice: {raw!r}. Enter 'text' or 'html'.")


def _prompt_target_fields(profile: dict) -> None:
    """Prompt for per-profile recipient and subject."""
    current_email = (profile.get("target_email") or "").strip()
    raw = input(f"  Recipient email [{current_email or 'env REPORT_EMAIL'}]: ").strip()
    profile["target_email"] = raw or current_email
    current_subject = (profile.get("target_subject") or "").strip()
    raw = input(f"  Email subject [{current_subject or 'auto-generated'}]: ").strip()
    profile["target_subject"] = raw or current_subject


def _configure_email_options(paths: SetupPaths, profile_name: str | None = None) -> None:
    config = _load_or_create_config(paths)
    if profile_name:
        profile = find_profile(config, profile_name)
        email = profile["email_report"]
        header = f"\nEmail report options for profile {profile_name!r}:"
    else:
        email = config["email_report"]
        profile = config["profiles"][0] if config.get("profiles") else None
        header = "\nEmail report options (stored in .github-usage/config.toml):"
    print(header)
    email["include_consumers"] = _prompt_yes_no(
        "Include top repository breakdowns (consumers of Actions minutes)?",
        email["include_consumers"],
    )
    email["include_artifact_storage"] = _prompt_yes_no(
        "Include Actions artifact storage details?", email["include_artifact_storage"]
    )
    email["include_release_assets"] = _prompt_yes_no(
        "Include release asset inventory (one extra API call per release)?",
        email["include_release_assets"],
    )
    email["max_repos"] = _prompt_int(
        "Max repositories to scan (caps API work; higher = slower, more complete)",
        int(email["max_repos"]),
    )
    email["email_format"] = _prompt_email_format(email["email_format"])
    email["skip_actions"] = _prompt_yes_no("Skip Actions section?", email["skip_actions"])
    email["skip_copilot"] = _prompt_yes_no("Skip Copilot section?", email["skip_copilot"])
    email["skip_lfs"] = _prompt_yes_no("Skip Git LFS section?", email["skip_lfs"])
    if profile is not None and profile_name:
        profile["email_report"] = email
        if config.get("reports"):
            for entry in config["reports"]:
                if entry["name"] == profile_name:
                    entry["email_report"] = dict(email)
                    break
        _prompt_target_fields(profile)
        if config.get("reports"):
            for entry in config["reports"]:
                if entry["name"] == profile_name:
                    entry["target_email"] = profile.get("target_email", "")
                    entry["target_subject"] = profile.get("target_subject", "")
                    break
    elif profile is not None:
        config["email_report"] = email
        if config.get("profiles"):
            config["profiles"][0]["email_report"] = email
    write_config(paths.config_file, config)
    print(f"Wrote {paths.config_file.relative_to(paths.root)}")
