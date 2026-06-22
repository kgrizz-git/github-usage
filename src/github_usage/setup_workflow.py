"""GitHub Actions workflow template renderer for ./setup.sh."""

from __future__ import annotations

import difflib
import os
import tempfile
from pathlib import Path

DEFAULT_WORKFLOW_CONFIG = {
    "cron": "0 9 * * 1",
    "include_consumers": False,
    "include_artifact_storage": False,
    "include_release_assets": False,
}


def workflow_path(root: Path) -> Path:
    """Return the absolute path to the email-report workflow file."""
    return root / ".github" / "workflows" / "email-report.yml"


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


def render_workflow(config: dict, root: Path | None = None) -> str:
    """Render email-report.yml from the template using values from github_actions config."""
    actual_root = root if root is not None else Path(__file__).resolve().parents[2]
    template_path = workflow_path(actual_root).with_suffix(".yml.template")
    if not template_path.is_file():
        raise FileNotFoundError(
            f"Template not found: {template_path}. "
            "Re-clone the repository or restore the file from git."
        )
    text = template_path.read_text(encoding="utf-8")
    ga = {**DEFAULT_WORKFLOW_CONFIG, **config.get("github_actions", {})}

    def bval(v: object) -> str:
        return "true" if v else "false"

    text = text.replace("__CRON__", ga["cron"])
    text = text.replace("__INCLUDE_CONSUMERS_DEFAULT__", bval(ga["include_consumers"]))
    text = text.replace(
        "__INCLUDE_ARTIFACT_STORAGE_DEFAULT__", bval(ga["include_artifact_storage"])
    )
    text = text.replace("__INCLUDE_RELEASE_ASSETS_DEFAULT__", bval(ga["include_release_assets"]))
    return text


def write_workflow(root: Path, text: str) -> None:
    """Atomically write the rendered workflow file with standard tracked-file permissions."""
    dest = workflow_path(root)
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
        tmp_path = None  # replace succeeded; nothing left to clean up
    finally:
        if tmp_path is not None and tmp_path.exists():
            tmp_path.unlink()
    os.chmod(dest, 0o644)


def diff_workflow(root: Path, new_text: str) -> str:
    """Return a unified diff between new_text and the current on-disk workflow file.

    Returns empty string when the file is absent or content is identical.
    """
    dest = workflow_path(root)
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
