"""GUI preference persistence for the Textual TUI."""

from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path

from ..setup_config import SetupPaths

_DEFAULT_TIMEOUT = 30.0
_DEFAULT_MAX_RETRIES = 3
_DEFAULT_CACHE_MAX_AGE_SECONDS = 3600


@dataclass
class GuiPreferences:
    """User preferences stored in ``.github-usage/gui.toml``."""

    last_view: str = "setup"
    last_profile: str = "default"
    report_timeout: float = _DEFAULT_TIMEOUT
    report_max_retries: int = _DEFAULT_MAX_RETRIES
    report_cache_max_age_seconds: int | None = None
    high_contrast: bool = False
    wizard_completed: bool = False
    dismissed_setup_wizard: bool = False

    def to_dict(self) -> dict:
        """Serialize preferences for TOML storage."""
        payload = {
            "last_view": self.last_view,
            "last_profile": self.last_profile,
            "report_timeout": self.report_timeout,
            "report_max_retries": self.report_max_retries,
            "high_contrast": self.high_contrast,
            "wizard_completed": self.wizard_completed,
            "dismissed_setup_wizard": self.dismissed_setup_wizard,
        }
        if self.report_cache_max_age_seconds is not None:
            payload["report_cache_max_age_seconds"] = self.report_cache_max_age_seconds
        return payload


def prefs_path(paths: SetupPaths) -> Path:
    """Return the path to the GUI preferences file."""
    return paths.config_dir / "gui.toml"


def load_gui_prefs(paths: SetupPaths) -> GuiPreferences:
    """Load GUI preferences or return defaults."""
    path = prefs_path(paths)
    if not path.is_file():
        return GuiPreferences()
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    gui = data.get("gui", data)
    cache_override = gui.get("report_cache_max_age_seconds")
    cache_seconds = None if cache_override is None else int(cache_override)
    return GuiPreferences(
        last_view=str(gui.get("last_view", "setup")),
        last_profile=str(gui.get("last_profile", "default")),
        report_timeout=float(gui.get("report_timeout", _DEFAULT_TIMEOUT)),
        report_max_retries=int(gui.get("report_max_retries", _DEFAULT_MAX_RETRIES)),
        report_cache_max_age_seconds=cache_seconds,
        high_contrast=bool(gui.get("high_contrast", False)),
        wizard_completed=bool(gui.get("wizard_completed", False)),
        dismissed_setup_wizard=bool(gui.get("dismissed_setup_wizard", False)),
    )


def save_gui_prefs(paths: SetupPaths, prefs: GuiPreferences) -> None:
    """Persist GUI preferences to disk."""
    path = prefs_path(paths)
    path.parent.mkdir(parents=True, exist_ok=True)
    p = prefs.to_dict()
    lines = [
        "# GUI preferences for github-usage Textual TUI.",
        "# Safe to edit locally.",
        "",
        "[gui]",
        f'last_view = "{p["last_view"]}"',
        f'last_profile = "{p["last_profile"]}"',
        f"report_timeout = {p['report_timeout']}",
        f"report_max_retries = {p['report_max_retries']}",
    ]
    if "report_cache_max_age_seconds" in p:
        lines.append(f"report_cache_max_age_seconds = {p['report_cache_max_age_seconds']}")
    lines.extend(
        [
            f"high_contrast = {'true' if p['high_contrast'] else 'false'}",
            f"wizard_completed = {'true' if p.get('wizard_completed') else 'false'}",
            f"dismissed_setup_wizard = {'true' if p.get('dismissed_setup_wizard') else 'false'}",
            "",
        ]
    )
    path.write_text("\n".join(lines), encoding="utf-8")
