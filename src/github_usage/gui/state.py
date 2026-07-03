"""Centralized application state for the Textual TUI."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

from ..gui_backend import (
    DEFAULT_PROFILE_NAME,
    load_profiles,
    load_setup_paths,
    read_secrets,
)
from ..setup_config import SetupPaths
from .prefs import GuiPreferences, load_gui_prefs, save_gui_prefs

Listener = Callable[[], None]


@dataclass
class AppState:
    """Single source of truth for profiles, secrets, and GUI preferences.

    Views subscribe via ``add_listener`` and refresh when ``reload`` or
    ``set_current_profile`` is called.
    """

    paths: SetupPaths = field(default_factory=load_setup_paths)
    profile_names: list[str] = field(default_factory=list)
    current_profile: str = DEFAULT_PROFILE_NAME
    secrets: dict[str, str] = field(default_factory=dict)
    config_error: str | None = None
    prefs: GuiPreferences = field(default_factory=GuiPreferences)
    _listeners: list[Listener] = field(default_factory=list, repr=False)

    def add_listener(self, callback: Listener) -> None:
        """Register a callback invoked when state changes."""
        self._listeners.append(callback)

    def remove_listener(self, callback: Listener) -> None:
        """Unregister a previously added listener."""
        if callback in self._listeners:
            self._listeners.remove(callback)

    def notify(self) -> None:
        """Notify all listeners of a state change."""
        for callback in list(self._listeners):
            callback()

    def reload(self) -> None:
        """Reload profiles, secrets, and preferences from disk."""
        self.config_error = None
        self.prefs = load_gui_prefs(self.paths)
        try:
            config = load_profiles(self.paths)
            self.profile_names = [p["name"] for p in config.get("profiles", [])]
            if self.prefs.last_profile in self.profile_names:
                self.current_profile = self.prefs.last_profile
            elif self.profile_names:
                self.current_profile = self.profile_names[0]
            else:
                self.current_profile = DEFAULT_PROFILE_NAME
        except FileNotFoundError:
            self.profile_names = []
            self.current_profile = DEFAULT_PROFILE_NAME
            self.config_error = "Config file not found. Run setup first."
        except PermissionError:
            self.profile_names = []
            self.config_error = "Permission denied reading config."
        except Exception as exc:
            self.profile_names = []
            self.config_error = str(exc)
        try:
            self.secrets = read_secrets(self.paths)
        except OSError:
            self.secrets = {}
        self.notify()

    def set_current_profile(
        self,
        name: str,
        *,
        persist: bool = True,
        notify: bool = True,
    ) -> None:
        """Update the active profile and optionally persist the choice."""
        changed = self.current_profile != name
        self.current_profile = name
        if persist:
            self.prefs.last_profile = name
            save_gui_prefs(self.paths, self.prefs)
        if notify and changed:
            self.notify()

    def set_last_view(self, view_id: str) -> None:
        """Remember the last active navigation view."""
        self.prefs.last_view = view_id
        save_gui_prefs(self.paths, self.prefs)

    def save_report_settings(self, timeout: float, max_retries: int) -> None:
        """Persist legacy report timeout/retry preferences."""
        self.prefs.report_timeout = timeout
        self.prefs.report_max_retries = max_retries
        save_gui_prefs(self.paths, self.prefs)
