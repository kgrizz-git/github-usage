"""HTTP retry helper for robust API communication."""

from __future__ import annotations

import email.utils
import http.client
import socket
import time
from collections.abc import Callable
from dataclasses import dataclass

# Rate Limit and 403 Policy:
# - The helper retries any status in RETRYABLE_STATUSES (408, 429, 500, 502, 503, 504) unconditionally.
# - It retries a 403 only when the response itself signals throttling: `Retry-After`
#   is present, `x-ratelimit-remaining` is `0`, or the body mentions a rate limit.
#   Every GitHub response carries `x-ratelimit-reset`, including plain permission
#   failures, so header presence alone must not select the retry path.
#   It does not retry 401, 404, or other 4xx.
# - The legacy 403+Retry-After branch in api.py is deleted since this helper
#   natively handles 403 rate limits.

DEFAULT_TIMEOUT_SECONDS = 30
DEFAULT_MAX_RETRIES = 3
DEFAULT_MAX_BACKOFF_SECONDS = 30
RETRYABLE_STATUSES = frozenset({408, 429, 500, 502, 503, 504})
RETRYABLE_EXCEPTIONS = (
    http.client.RemoteDisconnected,
    http.client.ResponseNotReady,
    http.client.IncompleteRead,
    ConnectionResetError,
    ConnectionRefusedError,
    socket.timeout,
    socket.gaierror,
)


@dataclass(frozen=True)
class Response:
    status: int
    body: bytes
    headers: http.client.HTTPMessage


def parse_rate_limit_headers(headers: http.client.HTTPMessage) -> float | None:
    """Return the float seconds to sleep based on Retry-After or x-ratelimit-reset, or None."""
    retry_after = headers.get("Retry-After")
    if retry_after is not None:
        try:
            return float(retry_after)
        except ValueError:
            parsed_date = email.utils.parsedate_tz(retry_after)
            if parsed_date is not None:
                timestamp = email.utils.mktime_tz(parsed_date)
                return max(0.0, timestamp - time.time())

    reset = headers.get("x-ratelimit-reset")
    if reset is not None:
        try:
            return max(0.0, float(reset) - time.time())
        except ValueError:
            pass

    return None


# Bodies GitHub uses for primary/secondary throttling; permission 403s say
# "Resource not accessible by ..." instead.
_RATE_LIMIT_MARKERS = ("rate limit", "abuse detection", "secondary rate")


def is_rate_limit_403(headers: http.client.HTTPMessage, body: bytes) -> bool:
    """Return True when a 403 response represents throttling, not a permission denial.

    GitHub attaches ``x-ratelimit-reset`` to ordinary 403s too, so the header's
    presence alone is not a rate-limit signal. A 403 counts as throttling when it
    carries ``Retry-After``, reports ``x-ratelimit-remaining: 0``, or names a rate
    limit in its body.
    """
    if headers.get("Retry-After") is not None:
        return True
    if (headers.get("x-ratelimit-remaining") or "").strip() == "0":
        return True
    text = body.decode("utf-8", errors="replace").lower()
    return any(marker in text for marker in _RATE_LIMIT_MARKERS)


def backoff_seconds(attempt: int, retry_after: float | None = None) -> float:
    """Calculate the number of seconds to sleep before the next retry."""
    if retry_after is not None:
        return min(retry_after, DEFAULT_MAX_BACKOFF_SECONDS)
    return min(float(2**attempt), DEFAULT_MAX_BACKOFF_SECONDS)


def request_with_retries(
    method: str,
    url: str,
    *,
    host: str,
    headers: dict[str, str],
    body: str | bytes | None = None,
    timeout: float | None = DEFAULT_TIMEOUT_SECONDS,
    max_retries: int = DEFAULT_MAX_RETRIES,
    sleep: Callable[[float], None] | None = None,
) -> Response:
    """Execute an HTTP request with automatic retries for transient errors."""
    if timeout is not None and timeout <= 0:
        if timeout == 0:
            timeout = None
        else:
            raise ValueError(f"timeout must be positive, got {timeout}")

    if sleep is None:
        sleep = time.sleep

    attempt = 0
    while True:
        conn = http.client.HTTPSConnection(host, timeout=timeout)
        try:
            conn.request(method, url, body=body, headers=headers)
            resp = conn.getresponse()
            response = Response(status=resp.status, body=resp.read(), headers=resp.headers)

            retry_after_val = None
            needs_retry = False

            if response.status in RETRYABLE_STATUSES or (
                response.status == 403 and is_rate_limit_403(response.headers, response.body)
            ):
                needs_retry = True
                retry_after_val = parse_rate_limit_headers(response.headers)

            if not needs_retry:
                return response

            if attempt >= max_retries:
                body_text = response.body.decode("utf-8", errors="replace")
                raise RuntimeError(f"API error {response.status}: {body_text[:200]}")

            sleep(backoff_seconds(attempt, retry_after_val))
            attempt += 1

        except RETRYABLE_EXCEPTIONS as e:
            if attempt >= max_retries:
                raise e
            sleep(backoff_seconds(attempt))
            attempt += 1
        finally:
            conn.close()
