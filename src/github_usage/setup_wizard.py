"""Interactive guided setup for github-usage (./start.sh setup entry point).

The wizard composes focused modules — see ``setup_email_config``,
``setup_secrets``, ``setup_workflow``, ``setup_config``, ``setup_ci``,
and ``setup_launchd`` for the actual prompts and actions. This file
keeps the menu dispatcher and orchestration.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

from . import cli
from .setup_ci import _configure_ci_secrets, _configure_dev_hooks
from .setup_config import (
    DEFAULT_PROFILE_NAME,
    SetupPaths,
    _configure_schedule,
    _default_profile,
    email_report_args,
    ensure_profiles,
    find_profile,
    is_minimally_configured,
    load_config,
    repo_root,
    status_lines,
    write_config,
)
from .setup_email_config import _configure_email_options
from .setup_launchd import (
    _configure_launchd,
    generate_plist,
    install_launch_agent,
    launch_agent_status,
)
from .setup_prompts import _prompt_yes_no, _wrap_description
from .setup_secrets import _apply_env, _configure_env_secrets
from .setup_workflow import _configure_github_actions, _render_and_offer_commit


def _setup_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="github-usage setup",
        description="Guided setup for local email reports, launchd, CI secrets, and dev hooks.",
    )
    parser.add_argument(
        "--status",
        action="store_true",
        help="Print setup status and exit (0 if minimally configured).",
    )
    parser.add_argument(
        "--verify",
        action="store_true",
        help="Run email-report --dry-run using local config and env.",
    )
    parser.add_argument(
        "--print-args",
        action="store_true",
        help="Print email-report CLI args derived from config.toml.",
    )
    parser.add_argument(
        "--profile",
        default=None,
        help="Report profile for --print-args or --verify (default profile: default).",
    )
    parser.add_argument(
        "--non-interactive",
        action="store_true",
        help="Skip prompts (use with --status or --verify).",
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=None,
        help="Repository root (defaults to auto-detected repo root).",
    )
    return parser


def _verify_setup(paths: SetupPaths, profile_name: str | None = None) -> int:
    if not paths.config_file.is_file():
        print("Error: missing .github-usage/config.toml. Run setup and configure report options.")
        return 1
    _apply_env(paths)
    config = load_config(paths.config_file)
    names = [profile_name] if profile_name else [p["name"] for p in config["profiles"]]
    for name in names:
        args = ["email-report", "--dry-run", *email_report_args(config, name)]
        code = cli.main(args)
        if code != 0:
            print(f"Verify failed for profile {name!r}.")
            return code
    return 0


def _regenerate_scheduled_artifacts(paths: SetupPaths) -> None:
    """Regenerate launchd plists and offer to update workflow files for all profiles."""
    config = load_config(paths.config_file) if paths.config_file.is_file() else None
    profile_names = [p["name"] for p in config["profiles"]] if config else [DEFAULT_PROFILE_NAME]
    for profile_name in profile_names:
        plist = generate_plist(paths, profile_name)
        print(f"Generated {plist.relative_to(paths.root)}")
    _render_and_offer_commit(paths)


def _manage_profiles(paths: SetupPaths) -> int:
    config = _load_or_create_config(paths)
    while True:
        config = load_config(paths.config_file) if paths.config_file.is_file() else config
        profiles = config.get("profiles") or []
        print("\nReport profiles:")
        if not profiles:
            print("  (none)")
        for profile in profiles:
            schedule = profile["schedule"]
            target = profile.get("target_email") or "(env REPORT_EMAIL)"
            print(
                f"  - {profile['name']}: to={target}, "
                f"schedule weekday={schedule.get('weekday')} "
                f"{schedule.get('hour'):02d}:{schedule.get('minute'):02d}"
            )
        print("\n  a) Add profile")
        print("  e) Edit profile")
        print("  d) Delete profile")
        print("  s) Save and regenerate schedules/workflows")
        print("  q) Back")
        action = input("Action [q]: ").strip().lower() or "q"
        if action in {"q", "quit", "back"}:
            return 0
        if action in {"a", "add"}:
            config = ensure_profiles(config)
            name = input("New profile name: ").strip()
            if not name:
                print("Profile name is required.")
                continue
            if any(p["name"] == name for p in config.get("profiles", [])):
                print(f"Profile {name!r} already exists.")
                continue
            config["profiles"].append(_default_profile(name=name))
            config["reports"] = [
                {
                    "name": p["name"],
                    "target_email": p.get("target_email", ""),
                    "target_subject": p.get("target_subject", ""),
                    "email_report": dict(p["email_report"]),
                    "schedule": dict(p["schedule"]),
                    "github_actions": dict(p["github_actions"]),
                }
                for p in config["profiles"]
            ]
            write_config(paths.config_file, config)
            _configure_email_options(paths, name)
            _configure_schedule(paths, name)
            _configure_github_actions(paths, name)
            continue
        if action in {"e", "edit"}:
            name = input("Profile name to edit: ").strip()
            if not name:
                continue
            try:
                find_profile(config, name)
            except KeyError:
                print(f"Unknown profile: {name!r}")
                continue
            _configure_email_options(paths, name)
            _configure_schedule(paths, name)
            _configure_github_actions(paths, name)
            continue
        if action in {"d", "delete"}:
            name = input("Profile name to delete: ").strip()
            if not name:
                continue
            if name == DEFAULT_PROFILE_NAME and len(config.get("profiles", [])) <= 1:
                print("Cannot delete the only profile.")
                continue
            config = ensure_profiles(config)
            config["profiles"] = [p for p in config["profiles"] if p["name"] != name]
            if not config["profiles"]:
                print("At least one profile must remain.")
                config["profiles"] = [_default_profile()]
            config["reports"] = [
                {
                    "name": p["name"],
                    "target_email": p.get("target_email", ""),
                    "target_subject": p.get("target_subject", ""),
                    "email_report": dict(p["email_report"]),
                    "schedule": dict(p["schedule"]),
                    "github_actions": dict(p["github_actions"]),
                }
                for p in config["profiles"]
            ]
            write_config(paths.config_file, config)
            print(f"Deleted profile {name!r}.")
            continue
        if action in {"s", "save"}:
            _regenerate_scheduled_artifacts(paths)
            if sys.platform == "darwin" and launch_agent_status(paths) != "not installed":
                print(_REINSTALL_REMINDER)
            return 0
        print("Unknown action.")


def _load_or_create_config(paths: SetupPaths):
    from .setup_config import _load_or_create_config as load_or_create

    return load_or_create(paths)


def _full_setup(paths: SetupPaths) -> int:
    _configure_env_secrets(paths)
    _configure_email_options(paths)
    _configure_schedule(paths)
    _configure_github_actions(paths)
    _regenerate_scheduled_artifacts(paths)
    code = _verify_setup(paths)
    if code != 0:
        print("Verify failed; fix auth or options before scheduling.")
        return code
    if sys.platform == "darwin" and _prompt_yes_no("\nInstall macOS LaunchAgent schedule?", True):
        install_code, message = install_launch_agent(paths)
        print(message)
        if install_code != 0:
            return install_code
    if _prompt_yes_no("\nConfigure GitHub Actions secrets with gh?", False):
        _configure_ci_secrets()
    if _prompt_yes_no("\nInstall developer pre-commit/pre-push hooks?", True):
        _configure_dev_hooks()
    print("\nSetup complete. Re-run `./start.sh setup` anytime to change options.")
    return 0


# Module-level menu handlers (lifted from inner closures of _interactive_menu
# to keep the dispatcher small). Each takes a SetupPaths (some ignore it)
# and returns an exit code.
def _secrets_only(paths: SetupPaths) -> int:
    _configure_env_secrets(paths)
    return 0


def _options_only(paths: SetupPaths) -> int:
    _configure_email_options(paths)
    return 0


def _hooks_only(_paths: SetupPaths) -> int:
    _configure_dev_hooks()
    return 0


def _ci_only(_paths: SetupPaths) -> int:
    _configure_ci_secrets()
    return 0


def _status_only(paths: SetupPaths) -> int:
    _print_status(paths)
    return 0


_REINSTALL_REMINDER = (
    "LaunchAgent is installed. Run option 5 (macOS launchd schedule) "
    "and choose install to apply the new schedule."
)


def _schedule_only(paths: SetupPaths) -> int:
    """Configure the schedule and regenerate the LaunchAgent plist."""
    _configure_schedule(paths)
    _regenerate_scheduled_artifacts(paths)
    if sys.platform == "darwin" and launch_agent_status(paths) != "not installed":
        print(_REINSTALL_REMINDER)
    return 0


def _github_actions_only(paths: SetupPaths) -> int:
    """Configure GitHub Actions workflow options and offer to write the rendered file."""
    _configure_github_actions(paths)
    _render_and_offer_commit(paths)
    return 0


_MENU_OPTIONS: list[tuple[str, str, str, callable]] = [
    (
        "1",
        "Recommended full setup",
        (
            "Walk through every step: local secrets, report options, schedule, "
            "GitHub Actions workflow, verification, and (optionally) install launchd, "
            "CI secrets, and developer hooks. Best for first-time setup."
        ),
        _full_setup,
    ),
    (
        "2",
        "Local email secrets only",
        (
            "Write .env.email-report (mode 600) with GITHUB_TOKEN, RESEND_API_KEY, "
            "REPORT_EMAIL, and RESEND_FROM. Use this if you only run reports locally."
        ),
        _secrets_only,
    ),
    (
        "3",
        "Report options only",
        (
            "Configure which sections appear in the email (consumers, artifact "
            "storage, release assets) and the max repositories to scan, stored in "
            ".github-usage/config.toml."
        ),
        _options_only,
    ),
    (
        "4",
        "Report schedule only",
        (
            "Configure the day of the week and time for your local reporting "
            "schedule and regenerate the LaunchAgent plist. Stored in "
            ".github-usage/config.toml. See option 5 to configure the separate "
            "GitHub Actions cron."
        ),
        _schedule_only,
    ),
    (
        "5",
        "GitHub Actions workflow",
        (
            "Configure the GitHub Actions cron schedule (UTC) and default report "
            "sections, then render and optionally write .github/workflows/email-report.yml. "
            "Manual workflow_dispatch runs in the GitHub UI still override these defaults "
            "per-run."
        ),
        _github_actions_only,
    ),
    (
        "6",
        "macOS launchd schedule",
        (
            "Generate, install, or remove the LaunchAgent plist that runs "
            "scripts/send-email-report.sh on your weekly schedule. macOS only."
        ),
        _configure_launchd,
    ),
    (
        "7",
        "GitHub Actions secrets",
        (
            "Push secrets to this repository with `gh secret set` so the scheduled "
            "GitHub Actions workflow can send the report. The GitHub token must be "
            "able to read your personal repos and user-billing endpoints "
            "(classic `repo`, or fine-grained with `Metadata: Read-only` and the "
            "account permission `Plan: Read-only`). Requires `gh` CLI auth."
        ),
        _ci_only,
    ),
    (
        "8",
        "Developer security hooks",
        (
            "Install pre-commit and pre-push hooks (ruff, ruff-format, gitleaks) "
            "to catch issues and leaked secrets before they leave your machine."
        ),
        _hooks_only,
    ),
    (
        "9",
        "Verify configuration",
        (
            "Run `email-report --dry-run` against your local config to confirm it "
            "works end-to-end without actually sending an email."
        ),
        _verify_setup,
    ),
    (
        "m",
        "Manage report profiles",
        (
            "Add, edit, or delete named report profiles with separate schedules, "
            "recipients, and GitHub Actions settings."
        ),
        _manage_profiles,
    ),
    (
        "0",
        "Show status",
        (
            "Print where setup files live, which env values are set (masked), and "
            "the LaunchAgent state. Exits non-zero if not minimally configured."
        ),
        _status_only,
    ),
]


def _print_menu() -> None:
    print("github-usage setup")
    print("==================")
    print("Configure local secrets, report options, schedules, CI secrets, and dev hooks.")
    print("First time? Choose option 1 to walk through everything in order.")
    print()
    for key, label, description, _ in _MENU_OPTIONS:
        print(f"  {key}) {label}")
        for line in _wrap_description(description):
            print(f"     {line}")
    print("  q) Quit")


def _print_status(paths: SetupPaths) -> int:
    for line in status_lines(paths):
        print(line)
    print(f"LaunchAgent: {launch_agent_status(paths)}")
    return 0


def _interactive_menu(paths: SetupPaths) -> int:
    _print_menu()
    choice = input("\nChoose an option [1]: ").strip().lower() or "1"
    if choice in {"q", "quit"}:
        return 0
    for key, _, _, handler in _MENU_OPTIONS:
        if key == choice:
            return int(handler(paths) or 0)
    print("Unknown option.")
    return 1


def run_setup(argv: Sequence[str] | None = None) -> int:
    """Run the setup subcommand."""
    parser = _setup_parser()
    try:
        args = parser.parse_args(list(argv or []))
    except SystemExit as exc:
        return int(exc.code or 0)

    paths = SetupPaths.from_root(args.root or repo_root())

    if args.print_args:
        config = load_config(paths.config_file)
        profile_name = args.profile or DEFAULT_PROFILE_NAME
        for item in email_report_args(config, profile_name):
            print(item)
        return 0

    if args.status:
        _print_status(paths)
        return 0 if is_minimally_configured(paths) else 1

    if args.verify:
        return _verify_setup(paths, args.profile)

    if args.non_interactive:
        print("Error: --non-interactive requires --status or --verify.")
        return 1

    if not sys.stdin.isatty():
        print("Error: interactive setup requires a TTY. Use --status or --verify.")
        return 1

    return _interactive_menu(paths)
