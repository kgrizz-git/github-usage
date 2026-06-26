"""Resend HTTP delivery for email reports (default_subject + send_email)."""

from __future__ import annotations

import json
from datetime import UTC, datetime


def default_subject(username: str, generated_at: str | None = None) -> str:
    """Return the default email subject."""
    day = generated_at[:10] if generated_at else datetime.now(tz=UTC).date().isoformat()
    return f"GitHub Usage Report for {username} - {day}"


def send_email(
    api_key: str,
    from_addr: str,
    to_addr: str,
    subject: str,
    body: str,
    html: str | None = None,
    timeout: float | None = None,
    max_retries: int | None = None,
) -> None:
    """Send a report through Resend with optional HTML body."""
    from . import http_retry

    payload_dict: dict[str, object] = {
        "from": from_addr,
        "to": [to_addr],
        "subject": subject,
        "text": body,
    }
    if html:
        payload_dict["html"] = html
    payload = json.dumps(payload_dict)
    response = http_retry.request_with_retries(
        "POST",
        "/emails",
        host="api.resend.com",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        body=payload,
        timeout=timeout if timeout is not None else http_retry.DEFAULT_TIMEOUT_SECONDS,
        max_retries=max_retries if max_retries is not None else http_retry.DEFAULT_MAX_RETRIES,
    )
    if response.status not in (200, 201):
        response_body = response.body.decode("utf-8", errors="replace")
        raise RuntimeError(f"Resend API error {response.status}: {response_body[:300]}")
