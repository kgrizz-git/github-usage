"""Redaction layer for file exports.

Strips or masks sensitive fields from report data before writing to a file.
Used only for file exports (not interactive terminal output or email body).

Invariants:
- ``redact_report_data`` returns a deep copy; the input is never mutated.
- Username redaction is by key (``data["username"]``); no generic regex is
  used to avoid false positives on SKU names and model names.
- Repo redaction is by key (``{"repo": ...}`` entries anywhere in the dict,
  recursively), so future sections are auto-covered.
- Text redaction matches email addresses and dollar amounts only; username
  redaction is skipped for text to avoid over-redaction of ordinary words.
- All redaction functions are idempotent.
"""

from __future__ import annotations

import copy
import re

REDACT_USERNAME = "[redacted-user]"
REDACT_REPO = "[redacted-repo]"
REDACT_EMAIL = "[redacted-email]"
REDACT_AMOUNT = "[redacted-amount]"

_EMAIL_PATTERN = re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}")
_DOLLAR_PATTERN = re.compile(r"\$[\d,]+\.?\d*")


def redact_report_data(data: dict) -> dict:
    """Return a deep-copied report data dict with sensitive fields redacted."""
    redacted = copy.deepcopy(data)
    if "username" in redacted:
        redacted["username"] = REDACT_USERNAME
    _redact_repos_in_place(redacted)
    _redact_strings_in_place(redacted)
    return redacted


def redact_text(text: str) -> str:
    """Apply email and dollar-amount redaction to a plain-text string."""
    text = _EMAIL_PATTERN.sub(REDACT_EMAIL, text)
    text = _DOLLAR_PATTERN.sub(REDACT_AMOUNT, text)
    return text


def _redact_strings_in_place(node) -> None:
    """Recursively replace string values containing dollar amounts.

    Plain string items inside lists (e.g., warnings, insights) are also
    scanned so they are redacted along with dict string values.
    """
    if isinstance(node, dict):
        for key, value in list(node.items()):
            if isinstance(value, str) and _DOLLAR_PATTERN.search(value):
                node[key] = _DOLLAR_PATTERN.sub(REDACT_AMOUNT, value)
            elif isinstance(value, dict | list):
                _redact_strings_in_place(value)
    elif isinstance(node, list):
        for index, item in enumerate(node):
            if isinstance(item, str) and _DOLLAR_PATTERN.search(item):
                node[index] = _DOLLAR_PATTERN.sub(REDACT_AMOUNT, item)
            elif isinstance(item, dict | list):
                _redact_strings_in_place(item)


def _redact_repos_in_place(node) -> None:
    """Recursively replace any ``"repo"`` string entry with the redaction marker."""
    if isinstance(node, dict):
        if "repo" in node and isinstance(node["repo"], str):
            node["repo"] = REDACT_REPO
        for value in node.values():
            _redact_repos_in_place(value)
    elif isinstance(node, list):
        for item in node:
            _redact_repos_in_place(item)
