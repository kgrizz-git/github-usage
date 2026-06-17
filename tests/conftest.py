"""Test fixtures and helpers for the export feature."""

import json
import os
from pathlib import Path

FIXTURES = Path(__file__).parent / "fixtures"


def load_export_report_data() -> dict:
    """Return a sanitized ReportData dict for export tests."""
    return json.loads((FIXTURES / "export_report_data.json").read_text())


def fake_token() -> str:
    """Return a fake GitHub token and inject it into the environment."""
    token = "ghp_fake_token_for_testing_only_0000000000000000"
    os.environ["GITHUB_TOKEN"] = token
    return token
