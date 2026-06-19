"""Generate and install macOS LaunchAgent plists for scheduled email reports."""

from __future__ import annotations

import os
import plistlib
import subprocess  # nosec B404
import sys
from pathlib import Path

from .setup_config import SetupPaths, load_config

LABEL = "com.github.github-usage.email-report"
LAUNCH_AGENT_NAME = f"{LABEL}.plist"


def generate_plist(paths: SetupPaths) -> Path:
    """Write a LaunchAgent plist using repo path and schedule config."""
    config = load_config(paths.config_file)
    schedule = config["schedule"]
    script_path = paths.root / "scripts" / "send-email-report.sh"
    paths.launchd_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "Label": LABEL,
        "ProgramArguments": [str(script_path.resolve())],
        "WorkingDirectory": str(paths.root.resolve()),
        "StartCalendarInterval": {
            "Weekday": int(schedule.get("weekday", 1)),
            "Hour": int(schedule.get("hour", 9)),
            "Minute": int(schedule.get("minute", 0)),
        },
        "StandardOutPath": str((paths.root / "reports" / "launchd.stdout.log").resolve()),
        "StandardErrorPath": str((paths.root / "reports" / "launchd.stderr.log").resolve()),
    }
    paths.launchd_plist.write_bytes(plistlib.dumps(payload))
    return paths.launchd_plist


def launch_agent_dest() -> Path:
    """Return the user LaunchAgents destination path."""
    return Path.home() / "Library" / "LaunchAgents" / LAUNCH_AGENT_NAME


def install_launch_agent(paths: SetupPaths) -> tuple[int, str]:
    """Install the generated plist into ~/Library/LaunchAgents."""
    if sys.platform != "darwin":
        return 1, "LaunchAgent install is only supported on macOS."
    plist = generate_plist(paths)
    dest = launch_agent_dest()
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(plist.read_bytes())
    uid = os.getuid()
    domain = f"gui/{uid}"
    bootout = subprocess.run(  # nosec
        ["launchctl", "bootout", domain, str(dest)],
        capture_output=True,
        text=True,
    )
    if bootout.returncode not in (0, 3, 113):
        return bootout.returncode, bootout.stderr.strip() or "launchctl bootout failed"
    bootstrap = subprocess.run(  # nosec
        ["launchctl", "bootstrap", domain, str(dest)],
        capture_output=True,
        text=True,
    )
    if bootstrap.returncode != 0:
        return bootstrap.returncode, bootstrap.stderr.strip() or "launchctl bootstrap failed"
    return 0, f"Installed LaunchAgent: {dest}"


def uninstall_launch_agent() -> tuple[int, str]:
    """Remove the LaunchAgent from ~/Library/LaunchAgents."""
    if sys.platform != "darwin":
        return 1, "LaunchAgent uninstall is only supported on macOS."
    dest = launch_agent_dest()
    if not dest.exists():
        return 0, "LaunchAgent is not installed."
    uid = os.getuid()
    domain = f"gui/{uid}"
    result = subprocess.run(  # nosec
        ["launchctl", "bootout", domain, str(dest)],
        capture_output=True,
        text=True,
    )
    dest.unlink(missing_ok=True)
    if result.returncode not in (0, 3, 113):
        return result.returncode, result.stderr.strip() or "launchctl bootout failed"
    return 0, f"Removed LaunchAgent: {dest}"


def launch_agent_status() -> str:
    """Return whether the LaunchAgent plist is installed."""
    dest = launch_agent_dest()
    return "installed" if dest.is_file() else "not installed"
