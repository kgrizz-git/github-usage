"""Email report formatting (plain-text and HTML) and Resend delivery."""

from __future__ import annotations

from .email_report_html import format_html_report as format_html_report
from .email_report_send import (
    default_subject as default_subject,
)
from .email_report_send import (
    send_email as send_email,
)
from .email_report_text import format_report_email as format_report_email
