"""Tests that GUI selector constants match their expected widget IDs.

This ensures that any refactoring of widget IDs will fail this test if the
corresponding constants are not also updated, mitigating the risk of the
indirection introduced for SonarCloud rule S1192.
"""

from github_usage.gui.views.email_report_view import _EMAIL_PREVIEW
from github_usage.gui.views.report_view import _REPORT_LOG
from github_usage.gui.views.runs_view import _RUNS_LOG
from github_usage.gui.views.schedules_view import (
    _INSTALL_LA_LABEL,
    _PROFILE_SELECT,
    _SCHED_LOG,
    _SCHEDULE_PICKER,
)
from github_usage.gui.views.setup_profiles_panel import _ONLY_PRIVATE, _ONLY_PUBLIC
from github_usage.gui.views.setup_verify_panel import _VERIFY_LOG
from github_usage.gui.wizard.setup_wizard_screen import (
    _WIZ_GA_PICKER,
    _WIZ_LOCAL_PICKER,
    _WIZ_ONLY_PRIVATE,
    _WIZ_ONLY_PUBLIC,
    _WIZ_VERIFY_LOG,
)


def test_gui_selectors_match_widget_ids():
    assert _EMAIL_PREVIEW == "#email-preview"
    assert _REPORT_LOG == "#report-log"
    assert _RUNS_LOG == "#runs-log"

    assert _SCHED_LOG == "#sched-log"
    assert _PROFILE_SELECT == "#profile-select"
    assert _SCHEDULE_PICKER == "#schedule-picker"
    assert _INSTALL_LA_LABEL == "Install LaunchAgent"

    assert _ONLY_PUBLIC == "#only-public"
    assert _ONLY_PRIVATE == "#only-private"
    assert _VERIFY_LOG == "#verify-log"

    assert _WIZ_LOCAL_PICKER == "#wizard-local-picker"
    assert _WIZ_GA_PICKER == "#wizard-ga-picker"
    assert _WIZ_ONLY_PUBLIC == "#wizard-only-public"
    assert _WIZ_ONLY_PRIVATE == "#wizard-only-private"
    assert _WIZ_VERIFY_LOG == "#wizard-verify-log"
