"""Interactive guided setup for github-usage (./setup.sh entry point)."""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess  # nosec B404
import sys
from collections.abc import Sequence
from pathlib import Path

from . import cli
from .setup_ci import _configure_ci_secrets
from .setup_config import (
    DEFAULT_EMAIL_REPORT,
    DEFAULT_SCHEDULE,
    SetupPaths,
    email_report_args,
    is_minimally_configured,
    load_config,
    read_env_file,
    repo_root,
    status_lines,
    write_config,
    write_env_file,
)
from .setup_launchd import (
    generate_plist,
    install_launch_agent,
    launch_agent_status,
    uninstall_launch_agent,
)
from .setup_prompts import _prompt_int, _prompt_value, _prompt_yes_no, _wrap_description
from .setup_workflow import (
    DEFAULT_WORKFLOW_CONFIG,
    diff_workflow,
    render_workflow,
    validate_cron,
    write_workflow,
)


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


def _load_or_create_config(paths: SetupPaths) -> dict:
    if paths.config_file.is_file():
        return load_config(paths.config_file)
    return {
        "email_report": dict(DEFAULT_EMAIL_REPORT),
        "schedule": dict(DEFAULT_SCHEDULE),
        "github_actions": dict(DEFAULT_WORKFLOW_CONFIG),
    }


def _configure_email_options(paths: SetupPaths) -> None:
    config = _load_or_create_config(paths)
    email = config["email_report"]
    print("\nEmail report options (stored in .github-usage/config.toml):")
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
    email["skip_actions"] = _prompt_yes_no("Skip Actions section?", email["skip_actions"])
    email["skip_copilot"] = _prompt_yes_no("Skip Copilot section?", email["skip_copilot"])
    email["skip_lfs"] = _prompt_yes_no("Skip Git LFS section?", email["skip_lfs"])
    config["email_report"] = email
    write_config(paths.config_file, config)
    print(f"Wrote {paths.config_file.relative_to(paths.root)}")


def _configure_github_actions(paths: SetupPaths) -> None:
    config = _load_or_create_config(paths)
    ga = config.get("github_actions", dict(DEFAULT_WORKFLOW_CONFIG))
    print("\nGitHub Actions workflow (stored in .github-usage/config.toml):")
    print("  Schedule always runs in UTC.")
    print("  Weekday: 0 or 7 = Sunday, 1 = Monday, ..., 6 = Saturday.")
    print("  Example cron expressions: '0 9 * * 1' (Mon 09:00), '0 14 * * 5' (Fri 14:00)")
    while True:
        raw = input(f"  Cron expression [{ga['cron']}]: ").strip()
        expr = raw or ga["cron"]
        try:
            ga["cron"] = validate_cron(expr)
            break
        except ValueError as exc:
            print(f"  {exc}")
    ga["include_consumers"] = _prompt_yes_no(
        "Include top repository breakdowns (consumers)?", ga["include_consumers"]
    )
    ga["include_artifact_storage"] = _prompt_yes_no(
        "Include Actions artifact storage details?", ga["include_artifact_storage"]
    )
    ga["include_release_assets"] = _prompt_yes_no(
        "Include release asset inventory?", ga["include_release_assets"]
    )
    config["github_actions"] = ga
    write_config(paths.config_file, config)
    print(f"Wrote {paths.config_file.relative_to(paths.root)}")


def _render_and_offer_commit(paths: SetupPaths) -> None:
    config = _load_or_create_config(paths)
    rendered = render_workflow(config, paths.root)
    diff = diff_workflow(paths.root, rendered)
    if not diff:
        print("Workflow file already up to date.")
        return
    print("\nProposed changes to .github/workflows/email-report.yml:")
    print(diff)
    if _prompt_yes_no("Write the updated workflow file?", True):
        write_workflow(paths.root, rendered)
        print("Wrote .github/workflows/email-report.yml")
        print(
            "  To apply: git add .github/workflows/email-report.yml"
            " && git commit -m 'chore(workflow): update email-report schedule'"
            " && git push"
        )


def _configure_schedule(paths: SetupPaths) -> None:
    config = _load_or_create_config(paths)
    schedule = config["schedule"]
    print("\nSchedule (local timezone, used by launchd):")
    schedule["weekday"] = _prompt_int("Weekday (0/7=Sun, 1=Mon)", int(schedule["weekday"]))
    schedule["hour"] = _prompt_int("Hour (0-23)", int(schedule["hour"]))
    schedule["minute"] = _prompt_int("Minute (0-59)", int(schedule["minute"]))
    config["schedule"] = schedule
    write_config(paths.config_file, config)
    print(f"Updated schedule in {paths.config_file.relative_to(paths.root)}")


def _resolve_github_token(existing: dict[str, str]) -> str:
    token = existing.get("GITHUB_TOKEN", "").strip()
    if token and _prompt_yes_no("Keep existing GITHUB_TOKEN in .env.email-report?", True):
        return token
    if shutil.which("gh"):
        try:
            result = subprocess.run(  # nosec
                ["gh", "auth", "token"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if (
                result.returncode == 0
                and result.stdout.strip()
                and _prompt_yes_no("Use token from `gh auth token`?", True)
            ):
                return result.stdout.strip()
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass
        if _prompt_yes_no("Run `gh auth refresh -h github.com -s user` now?", True):
            refresh = subprocess.run(["gh", "auth", "refresh", "-h", "github.com", "-s", "user"])  # nosec
            if refresh.returncode == 0:
                result = subprocess.run(  # nosec
                    ["gh", "auth", "token"],
                    capture_output=True,
                    text=True,
                    timeout=10,
                )
                if result.returncode == 0 and result.stdout.strip():
                    return result.stdout.strip()
    token = _prompt_value("GitHub token", secret=True)
    return token.strip()


def _configure_env_secrets(paths: SetupPaths) -> None:
    existing = read_env_file(paths.env_file)
    print("\nLocal email secrets (stored in .env.email-report, mode 600):")
    values = dict(existing)
    values["GITHUB_TOKEN"] = _resolve_github_token(existing)
    for key in ("RESEND_API_KEY", "REPORT_EMAIL", "RESEND_FROM"):
        current = existing.get(key, "")
        if current and _prompt_yes_no(f"Keep existing {key}?", True):
            values[key] = current
            continue
        secret = key != "REPORT_EMAIL"
        values[key] = _prompt_value(key, current, secret=secret).strip()
    write_env_file(paths.env_file, values)
    print(f"Wrote {paths.env_file.name} (permissions 600)")


def _apply_env(paths: SetupPaths) -> None:
    for key, value in read_env_file(paths.env_file).items():
        os.environ[key] = value


def _verify_setup(paths: SetupPaths) -> int:
    if not paths.config_file.is_file():
        print("Error: missing .github-usage/config.toml. Run setup and configure report options.")
        return 1
    _apply_env(paths)
    args = ["email-report", "--dry-run", *email_report_args(load_config(paths.config_file))]
    return cli.main(args)


def _configure_launchd(paths: SetupPaths) -> int:
    if sys.platform != "darwin":
        print("LaunchAgent setup is only available on macOS.")
        return 0
    print(f"\nLaunchAgent status: {launch_agent_status()}")
    print("The plist file controls when scripts/send-email-report.sh runs on this Mac.")
    print("Choose an action:")
    print("  i — install    (write the plist and load it into ~/Library/LaunchAgents)")
    print("  u — uninstall  (unload and remove the loaded agent)")
    print("  g — generate   (write the plist file but don't load it; review first)")
    print("  s — skip       (leave launchd alone)")
    action = input("Action [s]: ").strip().lower()
    if action in {"", "s", "skip"}:
        return 0
    if action in {"g", "generate"}:
        plist = generate_plist(paths)
        print(f"Generated {plist.relative_to(paths.root)}")
        return 0
    if action in {"u", "uninstall"}:
        code, message = uninstall_launch_agent()
        print(message)
        return code
    if action in {"i", "install"}:
        if not paths.config_file.is_file():
            _configure_schedule(paths)
        code, message = install_launch_agent(paths)
        print(message)
        return code
    print("Unknown action; skipped launchd changes.")
    return 0


def _configure_dev_hooks() -> None:
    if not shutil.which("pre-commit"):
        print("Install dev tools first: python3 -m pip install -e '.[dev]'")
        return
    print("\nDeveloper hooks:")
    if _prompt_yes_no("Install pre-commit hooks (commit + push)?", True):
        for args in (
            ["pre-commit", "install"],
            ["pre-commit", "install", "--hook-type", "pre-push"],
        ):
            result = subprocess.run(args, check=False)  # nosec
            if result.returncode != 0:
                print(f"Failed: {' '.join(args)}")
                return
        print("Installed pre-commit hooks for commit and push.")
    if shutil.which("gitleaks"):
        print("Gitleaks is available for local secret scanning.")
    else:
        print("Install gitleaks for local secret scanning (also bundled in pre-commit).")


def _full_setup(paths: SetupPaths) -> int:
    _configure_env_secrets(paths)
    _configure_email_options(paths)
    _configure_schedule(paths)
    _configure_github_actions(paths)
    _render_and_offer_commit(paths)
    plist = generate_plist(paths)
    print(f"Generated {plist.relative_to(paths.root)}")
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
    print("\nSetup complete. Re-run `./setup.sh` anytime to change options.")
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
    plist = generate_plist(paths)
    print(f"Generated {plist.relative_to(paths.root)}")
    if sys.platform == "darwin" and launch_agent_status() == "installed":
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


def _print_status(paths: SetupPaths) -> None:
    for line in status_lines(paths):
        print(line)
    print(f"LaunchAgent: {launch_agent_status()}")


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
        for item in email_report_args(config):
            print(item)
        return 0

    if args.status:
        _print_status(paths)
        return 0 if is_minimally_configured(paths) else 1

    if args.verify:
        return _verify_setup(paths)

    if args.non_interactive:
        print("Error: --non-interactive requires --status or --verify.")
        return 1

    if not sys.stdin.isatty():
        print("Error: interactive setup requires a TTY. Use --status or --verify.")
        return 1

    return _interactive_menu(paths)
