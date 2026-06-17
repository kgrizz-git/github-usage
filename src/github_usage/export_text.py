"""Plain-text writer for report exports.

Delegates to :func:`github_usage.email_report.format_report_email` for
dict input. The import is deferred to avoid a circular dependency if
``email_report`` ever imports from this module.
"""

from __future__ import annotations


def write(data, file_obj) -> None:
    """Write ``data`` as plain text to ``file_obj``.

    If ``data`` is a string, write it directly. If it is a dict, format
    it via :func:`github_usage.email_report.format_report_email`. A
    trailing newline is appended if missing.
    """
    if isinstance(data, str):
        body = data
    else:
        from . import email_report

        body = email_report.format_report_email(data)

    file_obj.write(body)
    if not body.endswith("\n"):
        file_obj.write("\n")
