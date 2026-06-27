"""GitHub Actions workflow template renderer for ./start.sh setup."""

from __future__ import annotations

import difflib
import os
import shlex
import tempfile
from pathlib import Path

from .setup_prompts import _prompt_yes_no

DEFAULT_PROFILE_NAME = "default"

DEFAULT_WORKFLOW_CONFIG = {
    "cron": "0 9 * * 1",
    "include_consumers": False,
    "include_artifact_storage": False,
    "include_release_assets": False,
}


def workflow_path(root: Path, profile_name: str = DEFAULT_PROFILE_NAME) -> Path:
    """Return the absolute path to an email-report workflow file."""
    workflows = root / ".github" / "workflows"
    if profile_name == DEFAULT_PROFILE_NAME:
        return workflows / "email-report.yml"
    return workflows / f"email-report-{profile_name}.yml"


def validate_cron(expr: str) -> str:
    """Validate a 5-field cron expression for GitHub Actions (always UTC).

    Accepts: * */n plain integers ranges (n-m) comma-separated sub-expressions.
    Rejects: @shortcuts seconds field Quartz/Spring extensions ? and L.
    Returns the expression unchanged on success; raises ValueError on error.
    """
    if "?" in expr or "L" in expr:
        raise ValueError(
            f"Invalid cron {expr!r}: '?' and 'L' are not supported by GitHub Actions "
            "(Quartz/Spring extensions). Use standard 5-field cron syntax."
        )
    fields = expr.split()
    if len(fields) != 5:
        raise ValueError(
            f"Invalid cron {expr!r}: expected 5 fields "
            f"(minute hour day-of-month month day-of-week), got {len(fields)}."
        )
    limits = [
        ("minute", 0, 59),
        ("hour", 0, 23),
        ("day-of-month", 1, 31),
        ("month", 1, 12),
        ("day-of-week", 0, 7),
    ]
    for field, (name, lo, hi) in zip(fields, limits, strict=False):
        _validate_cron_field(field, name, lo, hi)
    return expr


def _validate_cron_field(field: str, name: str, lo: int, hi: int) -> None:
    for sub in field.split(","):
        if sub == "*":
            continue
        if sub.startswith("*/"):
            step = sub[2:]
            if not step.isdigit() or int(step) < 1:
                raise ValueError(
                    f"Invalid cron {name} field {sub!r}: step must be a positive integer."
                )
            continue
        if "-" in sub:
            parts = sub.split("-", 1)
            if len(parts) != 2 or not parts[0].isdigit() or not parts[1].isdigit():
                raise ValueError(
                    f"Invalid cron {name} field {sub!r}: range must be two integers 'n-m'."
                )
            a, b = int(parts[0]), int(parts[1])
            if not (lo <= a <= hi) or not (lo <= b <= hi) or a > b:
                raise ValueError(
                    f"Invalid cron {name} field {sub!r}: values must be in [{lo},{hi}] "
                    "with start <= end."
                )
            continue
        if not sub.isdigit():
            raise ValueError(
                f"Invalid cron {name} field {sub!r}: "
                "expected integer, '*', '*/n', 'n-m', or comma-separated list."
            )
        val = int(sub)
        if not (lo <= val <= hi):
            raise ValueError(f"Invalid cron {name} value {val} out of range [{lo},{hi}].")


def _profile_suffix(profile_name: str) -> str:
    return "" if profile_name == DEFAULT_PROFILE_NAME else f"-{profile_name}"


def _shell_quote_args(args: list[str]) -> str:
    """Return a bash array literal for extra profile args."""
    if not args:
        return ""
    return " ".join(shlex.quote(item) for item in args)


def render_workflow(
    config: dict,
    root: Path | None = None,
    profile_name: str = DEFAULT_PROFILE_NAME,
) -> str:
    """Render an email-report workflow from the template for one profile."""
    actual_root = root if root is not None else Path(__file__).resolve().parents[2]
    template_path = workflow_path(actual_root, DEFAULT_PROFILE_NAME).with_suffix(".yml.template")
    if not template_path.is_file():
        raise FileNotFoundError(
            f"Template not found: {template_path}. "
            "Re-clone the repository or restore the file from git."
        )
    text = template_path.read_text(encoding="utf-8")
    from .setup_config import find_profile, profile_workflow_extra_args

    profile = find_profile(config, profile_name)
    ga = {**DEFAULT_WORKFLOW_CONFIG, **profile.get("github_actions", {})}

    def bval(v: object) -> str:
        return "true" if v else "false"

    suffix = _profile_suffix(profile_name)
    extra_args = profile_workflow_extra_args(config, profile_name)
    target_email = (profile.get("target_email") or "").strip()
    if target_email:
        target_email_expr = (
            f"${{{{ inputs.report_email || '{target_email}' || secrets.REPORT_EMAIL }}}}"
        )
    else:
        target_email_expr = "${{ inputs.report_email || secrets.REPORT_EMAIL }}"

    display_name = (
        "GitHub Usage Report" if suffix == "" else f"GitHub Usage Report ({profile_name})"
    )

    text = text.replace("__WORKFLOW_NAME__", display_name)
    text = text.replace("__PROFILE_SUFFIX__", suffix)
    text = text.replace("__CRON__", ga["cron"])
    text = text.replace("__INCLUDE_CONSUMERS_DEFAULT__", bval(ga["include_consumers"]))
    text = text.replace(
        "__INCLUDE_ARTIFACT_STORAGE_DEFAULT__", bval(ga["include_artifact_storage"])
    )
    text = text.replace("__INCLUDE_RELEASE_ASSETS_DEFAULT__", bval(ga["include_release_assets"]))
    text = text.replace("__TARGET_EMAIL__", target_email_expr)
    text = text.replace("__PROFILE_ARGS__", _shell_quote_args(extra_args))
    return text


def write_workflow(
    root: Path,
    text: str,
    profile_name: str = DEFAULT_PROFILE_NAME,
) -> None:
    """Atomically write the rendered workflow file with standard tracked-file permissions."""
    dest = workflow_path(root, profile_name)
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            dir=dest.parent,
            delete=False,
            suffix=".tmp",
            mode="w",
            encoding="utf-8",
        ) as tmp:
            tmp_path = Path(tmp.name)
            tmp.write(text)
        os.replace(tmp_path, dest)
        tmp_path = None
    finally:
        if tmp_path is not None and tmp_path.exists():
            tmp_path.unlink()
    os.chmod(dest, 0o644)


def diff_workflow(
    root: Path,
    new_text: str,
    profile_name: str = DEFAULT_PROFILE_NAME,
) -> str:
    """Return a unified diff between new_text and the current on-disk workflow file."""
    dest = workflow_path(root, profile_name)
    if not dest.is_file():
        return ""
    old_text = dest.read_text(encoding="utf-8")
    if old_text == new_text:
        return ""
    return "".join(
        difflib.unified_diff(
            old_text.splitlines(keepends=True),
            new_text.splitlines(keepends=True),
            fromfile=f"a/{dest.name}",
            tofile=f"b/{dest.name}",
        )
    )


def _configure_github_actions(paths, profile_name: str | None = None) -> None:
    from .setup_config import _load_or_create_config, find_profile, write_config

    config = _load_or_create_config(paths)
    if profile_name:
        ga = find_profile(config, profile_name)["github_actions"]
        label = f" for profile {profile_name!r}"
    else:
        ga = config.get("github_actions", dict(DEFAULT_WORKFLOW_CONFIG))
        label = ""
    print(f"\nGitHub Actions workflow{label} (stored in .github-usage/config.toml):")
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
    if profile_name:
        profile = find_profile(config, profile_name)
        profile["github_actions"] = ga
        if config.get("reports"):
            for entry in config["reports"]:
                if entry["name"] == profile_name:
                    entry["github_actions"] = dict(ga)
                    break
    else:
        config["github_actions"] = ga
        if config.get("profiles"):
            config["profiles"][0]["github_actions"] = ga
    write_config(paths.config_file, config)
    print(f"Wrote {paths.config_file.relative_to(paths.root)}")


def _render_and_offer_commit(paths, profile_name: str | None = None) -> None:
    from .setup_config import _load_or_create_config

    config = _load_or_create_config(paths)
    profile_names = (
        [profile_name] if profile_name else [p["name"] for p in config.get("profiles") or []]
    )
    if not profile_names:
        profile_names = [DEFAULT_PROFILE_NAME]

    for name in profile_names:
        rendered = render_workflow(config, paths.root, name)
        diff = diff_workflow(paths.root, rendered, name)
        if not diff:
            print(f"Workflow file for profile {name!r} already up to date.")
            continue
        dest = workflow_path(paths.root, name)
        print(f"\nProposed changes to {dest.relative_to(paths.root)}:")
        print(diff)
        if _prompt_yes_no("Write the updated workflow file?", True):
            write_workflow(paths.root, rendered, name)
            print(f"Wrote {dest.relative_to(paths.root)}")
            print(
                f"  To apply: git add {dest.relative_to(paths.root)}"
                f" && git commit -m 'chore(workflow): update email-report schedule'"
                f" && git push"
            )
