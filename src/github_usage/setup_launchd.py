"""Generate and install macOS LaunchAgent plists for scheduled email reports."""

from __future__ import annotations

import os
import plistlib
import subprocess  # nosec B404
import sys
from pathlib import Path

from .setup_config import DEFAULT_PROFILE_NAME, SetupPaths, find_profile, load_config

LEGACY_LABEL = "com.github.github-usage.email-report"
LEGACY_LAUNCH_AGENT_NAME = f"{LEGACY_LABEL}.plist"


def label_for(profile_name: str) -> str:
    """Return the LaunchAgent label for a report profile."""
    return f"com.github.github-usage.email-report.{profile_name}"


def launch_agent_dest(profile_name: str) -> Path:
    """Return the user LaunchAgents destination path for a profile."""
    return Path.home() / "Library" / "LaunchAgents" / f"{label_for(profile_name)}.plist"


def legacy_launch_agent_dest() -> Path:
    """Return the legacy single-profile LaunchAgent path."""
    return Path.home() / "Library" / "LaunchAgents" / LEGACY_LAUNCH_AGENT_NAME


def generate_plist(paths: SetupPaths, profile_name: str = DEFAULT_PROFILE_NAME) -> Path:
    """Write a LaunchAgent plist for one profile using its schedule config."""
    config = load_config(paths.config_file)
    profile = find_profile(config, profile_name)
    schedule = profile["schedule"]
    script_path = paths.root / "scripts" / "send-email-report.sh"
    paths.launchd_dir.mkdir(parents=True, exist_ok=True)
    plist_path = paths.launchd_plist_for(profile_name)
    reports_dir = paths.root / "reports"
    payload = {
        "Label": label_for(profile_name),
        "ProgramArguments": [str(script_path.resolve()), "--profile", profile_name],
        "WorkingDirectory": str(paths.root.resolve()),
        "StartCalendarInterval": {
            "Weekday": int(schedule.get("weekday", 1)),
            "Hour": int(schedule.get("hour", 9)),
            "Minute": int(schedule.get("minute", 0)),
        },
        "StandardOutPath": str((reports_dir / f"launchd-{profile_name}.stdout.log").resolve()),
        "StandardErrorPath": str((reports_dir / f"launchd-{profile_name}.stderr.log").resolve()),
    }
    plist_path.write_bytes(plistlib.dumps(payload))
    return plist_path


def _bootout_plist(dest: Path) -> tuple[int, str]:
    uid = os.getuid()
    domain = f"gui/{uid}"
    result = subprocess.run(  # nosec
        ["launchctl", "bootout", domain, str(dest)],
        capture_output=True,
        text=True,
    )
    if result.returncode not in (0, 3, 113):
        return result.returncode, result.stderr.strip() or "launchctl bootout failed"
    return 0, ""


def _bootstrap_plist(dest: Path) -> tuple[int, str]:
    uid = os.getuid()
    domain = f"gui/{uid}"
    result = subprocess.run(  # nosec
        ["launchctl", "bootstrap", domain, str(dest)],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return result.returncode, result.stderr.strip() or "launchctl bootstrap failed"
    return 0, ""


def _profile_names(paths: SetupPaths) -> list[str]:
    if paths.config_file.is_file():
        config = load_config(paths.config_file)
        return [p["name"] for p in config["profiles"]]
    return [DEFAULT_PROFILE_NAME]


def _remove_legacy_plist() -> None:
    dest = legacy_launch_agent_dest()
    if dest.exists():
        _bootout_plist(dest)
        dest.unlink(missing_ok=True)


def install_launch_agent(paths: SetupPaths) -> tuple[int, str]:
    """Install LaunchAgent plists for every configured profile."""
    if sys.platform != "darwin":
        return 1, "LaunchAgent install is only supported on macOS."
    messages: list[str] = []
    for profile_name in _profile_names(paths):
        plist = generate_plist(paths, profile_name)
        dest = launch_agent_dest(profile_name)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(plist.read_bytes())
        code, message = _bootout_plist(dest)
        if code != 0:
            return code, message
        code, message = _bootstrap_plist(dest)
        if code != 0:
            return code, message
        messages.append(f"Installed LaunchAgent for {profile_name}: {dest}")
    _remove_legacy_plist()
    return 0, "\n".join(messages) if messages else "Installed LaunchAgents."


def uninstall_launch_agent(paths: SetupPaths | None = None) -> tuple[int, str]:
    """Remove LaunchAgent plists for all profiles and the legacy plist."""
    if sys.platform != "darwin":
        return 1, "LaunchAgent uninstall is only supported on macOS."
    removed: list[str] = []
    profile_names = _profile_names(paths) if paths and paths.config_file.is_file() else []
    if not profile_names:
        profile_names = [DEFAULT_PROFILE_NAME]
    for profile_name in profile_names:
        dest = launch_agent_dest(profile_name)
        if dest.exists():
            code, message = _bootout_plist(dest)
            if code != 0:
                return code, message
            dest.unlink(missing_ok=True)
            removed.append(str(dest))
    legacy = legacy_launch_agent_dest()
    if legacy.exists():
        code, message = _bootout_plist(legacy)
        if code != 0:
            return code, message
        legacy.unlink(missing_ok=True)
        removed.append(str(legacy))
    if not removed:
        return 0, "LaunchAgent is not installed."
    return 0, "Removed LaunchAgent(s):\n" + "\n".join(removed)


def launch_agent_status(paths: SetupPaths | None = None) -> str:
    """Return a summary of installed LaunchAgent plists."""
    if sys.platform != "darwin":
        return "not supported (non-macOS)"
    installed: list[str] = []
    names = (
        _profile_names(paths) if paths and paths.config_file.is_file() else [DEFAULT_PROFILE_NAME]
    )
    for profile_name in names:
        if launch_agent_dest(profile_name).is_file():
            installed.append(profile_name)
    if legacy_launch_agent_dest().is_file():
        installed.append("(legacy)")
    if not installed:
        return "not installed"
    return "installed: " + ", ".join(installed)


def _configure_launchd(paths) -> int:
    import sys

    if sys.platform != "darwin":
        print("LaunchAgent setup is only available on macOS.")
        return 0
    print(f"\nLaunchAgent status: {launch_agent_status(paths)}")
    print("The plist file controls when scripts/send-email-report.sh runs on this Mac.")
    print("Choose an action:")
    print("  i — install    (write plists and load them into ~/Library/LaunchAgents)")
    print("  u — uninstall  (unload and remove loaded agents)")
    print("  g — generate   (write plist files but don't load them; review first)")
    print("  s — skip       (leave launchd alone)")
    action = input("Action [s]: ").strip().lower()
    if action in {"", "s", "skip"}:
        return 0
    if action in {"g", "generate"}:
        for profile_name in _profile_names(paths):
            plist = generate_plist(paths, profile_name)
            print(f"Generated {plist.relative_to(paths.root)}")
        return 0
    if action in {"u", "uninstall"}:
        code, message = uninstall_launch_agent(paths)
        print(message)
        return code
    if action in {"i", "install"}:
        if not paths.config_file.is_file():
            from .setup_config import _configure_schedule

            _configure_schedule(paths)
        code, message = install_launch_agent(paths)
        print(message)
        return code
    print("Unknown action; skipped launchd changes.")
    return 0
