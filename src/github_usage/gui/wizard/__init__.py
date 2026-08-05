"""Guided setup wizard for the Textual TUI."""

try:
    from .setup_wizard_screen import SetupWizardScreen

    __all__ = ["SetupWizardScreen"]
except ModuleNotFoundError as exc:
    if exc.name is None or not exc.name.startswith("textual"):
        raise
