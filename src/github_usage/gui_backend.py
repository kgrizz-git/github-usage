"""Public backend services for the Textual TUI (no UI imports).

Wraps setup, reporting, and drift logic so ``src/github_usage/gui/`` views
never import private ``_``-prefixed helpers directly.
"""

from __future__ import annotations

import io
import os
from contextlib import redirect_stderr, redirect_stdout
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from . import cli, export_report
from .auth import resolve_token
from .cli_email_report import _init_github_api
from .cli_runs import list_local_runs
from .setup_config import (
    SetupPaths,
    _default_profile,
    _profile_to_report_entry,
    email_report_args,
    find_profile,
    is_minimally_configured,
    load_config,
    load_report_profiles,
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
)
from .setup_secrets import _apply_env
from .setup_workflow import (
    render_workflow,
    validate_cron,
    write_workflow,
)


@dataclass
class VerifyResult:
    """Outcome of a configuration dry-run verification."""

    exit_code: int
    output: str


@dataclass
class DriftCheckResult:
    """Structured drift check outcome."""

    exit_code: int
    rows: list[dict]
    remote: str
    default_branch: str | None
    messages: list[str]


def load_setup_paths(root: Path | None = None) -> SetupPaths:
    """Return resolved setup artifact paths for the repository."""
    return SetupPaths.from_root(root or repo_root())


def read_secrets(paths: SetupPaths) -> dict[str, str]:
    """Read ``.env.email-report`` key/value pairs."""
    return read_env_file(paths.env_file)


def write_secrets(paths: SetupPaths, values: dict[str, str]) -> None:
    """Write ``.env.email-report`` at mode 600."""
    write_env_file(paths.env_file, values)


def load_profiles(paths: SetupPaths) -> dict:
    """Load config.toml with normalized ``profiles`` list."""
    if paths.config_file.is_file():
        return load_config(paths.config_file)
    profiles = [_default_profile()]
    return {"profiles": profiles, "reports": [_profile_to_report_entry(profiles[0])]}


def save_profiles(paths: SetupPaths, config: dict) -> None:
    """Persist profile configuration to config.toml."""
    profiles = config.get("profiles") or load_report_profiles(config)
    config["profiles"] = profiles
    config["reports"] = [_profile_to_report_entry(p) for p in profiles]
    write_config(paths.config_file, config)


def add_profile(config: dict, name: str) -> dict:
    """Append a new named profile; raises ``ValueError`` on duplicate name."""
    name = name.strip()
    if not name:
        raise ValueError("Profile name is required.")
    profiles = list(config.get("profiles") or load_report_profiles(config))
    if any(p["name"] == name for p in profiles):
        raise ValueError(f"Profile {name!r} already exists.")
    profiles.append(_default_profile(name=name))
    config["profiles"] = profiles
    config["reports"] = [_profile_to_report_entry(p) for p in profiles]
    return config


def delete_profile(config: dict, name: str) -> dict:
    """Remove a profile; keeps at least one profile."""
    profiles = list(config.get("profiles") or load_report_profiles(config))
    if len(profiles) <= 1:
        raise ValueError("Cannot delete the only profile.")
    remaining = [p for p in profiles if p["name"] != name]
    if len(remaining) == len(profiles):
        raise KeyError(name)
    profiles = remaining or [_default_profile()]
    config["profiles"] = profiles
    config["reports"] = [_profile_to_report_entry(p) for p in profiles]
    return config


def update_profile(config: dict, profile: dict) -> dict:
    """Replace one profile dict in config by name."""
    profiles = list(config.get("profiles") or load_report_profiles(config))
    name = profile["name"]
    for index, existing in enumerate(profiles):
        if existing["name"] == name:
            profiles[index] = profile
            config["profiles"] = profiles
            config["reports"] = [_profile_to_report_entry(p) for p in profiles]
            return config
    raise KeyError(name)


def verify_configuration(paths: SetupPaths, profile_name: str | None = None) -> VerifyResult:
    """Run ``email-report --dry-run`` for each profile with captured output."""
    buffer = io.StringIO()
    if not paths.config_file.is_file():
        return VerifyResult(
            1,
            "Error: missing .github-usage/config.toml. Configure report options first.",
        )
    _apply_env(paths)
    config = load_config(paths.config_file)
    names = [profile_name] if profile_name else [p["name"] for p in config["profiles"]]
    exit_code = 0
    with redirect_stdout(buffer), redirect_stderr(buffer):
        for name in names:
            args = ["email-report", "--dry-run", *email_report_args(config, name)]
            code = cli.main(args)
            if code != 0:
                buffer.write(f"Verify failed for profile {name!r}.\n")
                exit_code = code
                break
    return VerifyResult(exit_code, buffer.getvalue())


def status_summary(paths: SetupPaths) -> dict[str, Any]:
    """Return setup status lines and LaunchAgent state."""
    return {
        "lines": status_lines(paths),
        "launch_agent": launch_agent_status(paths),
        "configured": is_minimally_configured(paths),
    }


def apply_env(paths: SetupPaths) -> None:
    """Load secrets from disk into ``os.environ``."""
    _apply_env(paths)


def list_scheduled_runs(paths: SetupPaths, profile_filter: str | None = None) -> list[dict]:
    """Return local scheduled-run rows from config and workflow files."""
    config = load_profiles(paths)
    return list_local_runs(config, paths, profile_filter)


def formatted_scheduled_runs(
    paths: SetupPaths, profile_filter: str | None = None
) -> list[dict[str, str]]:
    """Return scheduled-run rows with display-ready schedule text."""
    from .cli_runs import _describe_profile, _format_schedule

    rows = list_scheduled_runs(paths, profile_filter)
    formatted: list[dict[str, str]] = []
    for row in rows:
        profile = row["profile"]
        formatted.append(
            {
                "active": str(row.get("active", "?")),
                "profile_label": f"{profile} ({_describe_profile(profile)})",
                "source": str(row.get("source", "?")),
                "schedule": _format_schedule(row),
            }
        )
    return formatted


def check_workflow_drift(
    paths: SetupPaths,
    profile_name: str | None = None,
    *,
    skip_fetch: bool = False,
) -> DriftCheckResult:
    """Run full git drift orchestration; return structured rows."""
    from . import cli_runs_diff

    messages: list[str] = []
    root = paths.root
    prereq_err = cli_runs_diff.check_prerequisites(root)
    if prereq_err is not None:
        return DriftCheckResult(1, [], "", None, [prereq_err])

    candidate_path = None
    if profile_name:
        from .setup_workflow import workflow_path

        candidate_path = workflow_path(root, profile_name)
        if not candidate_path.is_file():
            return DriftCheckResult(
                1,
                [],
                "",
                None,
                [f"No workflow file for profile {profile_name!r}."],
            )

    skip = skip_fetch or os.environ.get("GITHUB_USAGE_SKIP_FETCH") == "1"
    remote = cli_runs_diff.resolve_remote_name(root)
    fetched, _ = cli_runs_diff.fetch_remote(
        root, remote, skip_fetch=skip, env=cli_runs_diff.GIT_ENV
    )
    default_branch = cli_runs_diff.resolve_default_branch(root, remote)
    rows = cli_runs_diff.classify_drift(root, remote, default_branch, candidate_path=candidate_path)
    if (not fetched) and default_branch and not skip:
        messages.append(
            cli_runs_diff.FETCH_FALLBACK_WARNING_TEMPLATE.format(
                remote=remote, default_branch=default_branch
            )
        )
    return DriftCheckResult(0, rows, remote, default_branch, messages)


def regenerate_launchd_plist(paths: SetupPaths, profile_name: str) -> Path:
    """Generate a LaunchAgent plist for one profile."""
    return generate_plist(paths, profile_name)


def install_launch_agent_for_paths(paths: SetupPaths) -> tuple[int, str]:
    """Install LaunchAgents for all configured profiles (macOS only)."""
    return install_launch_agent(paths)


def get_launch_agent_status(paths: SetupPaths) -> str:
    """Return LaunchAgent install state summary."""
    return launch_agent_status(paths)


def regenerate_workflow_file(paths: SetupPaths, profile_name: str) -> Path:
    """Render and write the GitHub Actions workflow YAML for one profile."""
    config = load_profiles(paths)
    text = render_workflow(config, paths.root, profile_name)
    write_workflow(paths.root, text, profile_name)
    from .setup_workflow import workflow_path

    return workflow_path(paths.root, profile_name)


def configure_schedule_fields(
    paths: SetupPaths,
    profile_name: str,
    *,
    weekday: int,
    hour: int,
    minute: int,
) -> None:
    """Update local launchd schedule fields for one profile."""
    config = load_profiles(paths)
    profile = find_profile(config, profile_name)
    profile["schedule"] = {
        "weekday": int(weekday),
        "hour": int(hour),
        "minute": int(minute),
    }
    update_profile(config, profile)
    save_profiles(paths, config)


def configure_github_actions_fields(
    paths: SetupPaths,
    profile_name: str,
    *,
    cron: str,
    include_consumers: bool,
    include_artifact_storage: bool,
    include_release_assets: bool,
) -> None:
    """Update GitHub Actions cron and section defaults for one profile."""
    cron = validate_cron(cron.strip())
    config = load_profiles(paths)
    profile = find_profile(config, profile_name)
    profile["github_actions"] = {
        **profile.get("github_actions", {}),
        "cron": cron,
        "include_consumers": include_consumers,
        "include_artifact_storage": include_artifact_storage,
        "include_release_assets": include_release_assets,
    }
    update_profile(config, profile)
    save_profiles(paths, config)


def run_legacy_report_data(
    *,
    token: str | None = None,
    timeout: float = 30.0,
    max_retries: int = 3,
) -> tuple[int, dict | None, str | None]:
    """Fetch legacy report data; return ``(exit_code, data, username)``."""
    resolved = token or resolve_token(argv=[])
    if not resolved:
        return 1, None, None
    api_result = _init_github_api(resolved, timeout, max_retries)
    if isinstance(api_result, int):
        return api_result, None, None
    api, username = api_result
    try:
        from .legacy_report_data import build_legacy_report_data

        data = build_legacy_report_data(
            api,
            username,
            max_repos=100,
            warn_over=None,
            include_release_assets=False,
        )
        return 0, data, username
    except (RuntimeError, ValueError) as exc:
        return 1, None, str(exc)


def export_legacy_report(
    data: dict,
    username: str,
    export_format: str,
    output_path: str | None,
) -> tuple[int, str]:
    """Export report data to a file; return ``(exit_code, message)``."""
    try:
        path = export_report.export(
            data,
            export_format,
            output_path=output_path,
            username=username,
            month=None,
            redact_data=True,
        )
        return 0, f"Exported to: {path}"
    except (RuntimeError, ValueError, ImportError) as exc:
        return 1, str(exc)


def run_email_dry_run(
    paths: SetupPaths,
    profile_name: str,
    *,
    timeout: float = 30.0,
    max_retries: int = 3,
) -> tuple[int, str]:
    """Build email report body without sending; return ``(exit_code, body)``."""
    buffer = io.StringIO()
    _apply_env(paths)
    config = load_profiles(paths)
    args = ["email-report", "--dry-run", *email_report_args(config, profile_name)]
    with redirect_stdout(buffer), redirect_stderr(buffer):
        code = cli.main([*args, "--timeout", str(timeout), "--max-retries", str(max_retries)])
    return code, buffer.getvalue()


def send_email_report(
    paths: SetupPaths,
    profile_name: str,
    *,
    timeout: float = 30.0,
    max_retries: int = 3,
) -> tuple[int, str]:
    """Send email report for one profile; return ``(exit_code, message)``."""
    buffer = io.StringIO()
    _apply_env(paths)
    config = load_profiles(paths)
    args = ["email-report", *email_report_args(config, profile_name)]
    with redirect_stdout(buffer), redirect_stderr(buffer):
        code = cli.main([*args, "--timeout", str(timeout), "--max-retries", str(max_retries)])
    return code, buffer.getvalue() if code != 0 else "Email report sent."
