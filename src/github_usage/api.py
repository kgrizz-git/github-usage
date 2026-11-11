"""GitHub REST API client for github-usage."""

from __future__ import annotations

import json
import urllib.parse
from typing import TypedDict

from . import __version__


class RequestStats(TypedDict):
    """Measured API usage: total logical calls plus a per-resource breakdown."""

    actual_requests: int
    actual_requests_by_resource: dict[str, int]


class _RequestLogEntry(TypedDict):
    """One counted logical API call; ``status`` is None when no response was observed."""

    method: str
    path: str
    status: int | None


# GitHub list endpoints that return {total_count, <collection>: [...]} instead of a bare array.
_COLLECTION_KEYS = ("workflow_runs", "artifacts", "workflows")

# All stats resource buckets, in classification order. Billing paths live
# under ``/users/...``, so billing is matched by its ``/settings/billing/``
# segment first (defensive ordering).
_RESOURCE_BUCKETS = ("billing", "user", "rate_limit", "actions", "repos", "other")


# Resource buckets for request stats, evaluated in order: billing paths start
# with ``/users/...`` so billing must be matched before the user prefix.
def _classify_request_path(path: str) -> str:
    """Map a request path to a stats resource bucket."""
    if "/settings/billing/" in path:
        return "billing"
    if path == "/user" or path.startswith("/user/"):
        return "user"
    if path.startswith("/rate_limit"):
        return "rate_limit"
    if path.startswith("/repos/"):
        parts = path.split("/")
        if len(parts) > 4 and parts[4] == "actions":
            return "actions"
        return "repos"
    return "other"


class GitHubAPI:
    def __init__(self, token, timeout=None, max_retries=None):
        from . import http_retry

        self.token = token
        self.timeout = timeout if timeout is not None else http_retry.DEFAULT_TIMEOUT_SECONDS
        self.max_retries = (
            max_retries if max_retries is not None else http_retry.DEFAULT_MAX_RETRIES
        )
        # Request accounting for the API-usage report. Single-threaded use
        # only: reports never share a client across threads (GUI workers each
        # build their own client; see gui_backend.run_legacy_report_data).
        self.request_count: int = 0
        self.request_log: list[_RequestLogEntry] = []
        self.base = "https://api.github.com"
        self.headers = {
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": f"github-usage-report/{__version__} (+https://github.com/kgrizz-git/github-usage)",
        }

    def _record_request_start(self, method: str, path: str) -> _RequestLogEntry:
        """Count one logical API call and open its request-log entry.

        The entry's ``status`` is filled in once a response is observed;
        ``None`` means no response was observed at this layer (transport
        failure, or a retryable 5xx that exhausted retries).
        """
        self.request_count += 1
        entry: _RequestLogEntry = {"method": method, "path": path, "status": None}
        self.request_log.append(entry)
        return entry

    def get_request_stats(self) -> RequestStats:
        """Return actual request totals plus a per-resource breakdown.

        ``actual_requests`` is derived from the log so it cannot drift from
        the breakdown. Only aggregates are exposed: ``request_log`` entries
        (raw paths) never enter report data, since they would bypass the
        export redaction layer.
        """
        by_resource: dict[str, int] = {bucket: 0 for bucket in _RESOURCE_BUCKETS}
        for entry in self.request_log:
            bucket = _classify_request_path(entry["path"])
            by_resource[bucket] = by_resource.get(bucket, 0) + 1
        return {
            "actual_requests": len(self.request_log),
            "actual_requests_by_resource": by_resource,
        }

    def request(self, method, path, params=None):
        url = path
        if not url.startswith("/"):
            url = "/" + url
        entry = self._record_request_start(method, url)

        if params:
            query = urllib.parse.urlencode(params)
            if "?" in url:
                url += "&" + query
            else:
                url += "?" + query

        req_headers = {**self.headers}
        from . import http_retry

        response = http_retry.request_with_retries(
            method,
            url,
            host="api.github.com",
            headers=req_headers,
            timeout=self.timeout,
            max_retries=self.max_retries,
        )
        entry["status"] = response.status

        data = response.body.decode("utf-8")
        if response.status in (200, 201, 202, 204):
            if data:
                try:
                    return json.loads(data)
                except json.JSONDecodeError:
                    raise RuntimeError(
                        f"API returned success {response.status} but invalid JSON: {data[:200]}"
                    ) from None
            return {}
        elif response.status == 404:
            # Check if this is a billing endpoint that needs elevated access
            if "billing" in path and "settings" in path:
                raise RuntimeError(
                    f"API error 404 on billing endpoint '{path}'. "
                    f"This usually means your token does not have access "
                    f"to this billing endpoint."
                )
            raise RuntimeError(f"API error 404: {data[:200]}")
        else:
            raise RuntimeError(f"API error {response.status}: {data[:200]}")

    def request_raw(self, method, path, params=None):
        """Helper to get raw Response object containing headers (like Link)"""
        url = path
        if not url.startswith("/"):
            url = "/" + url
        entry = self._record_request_start(method, url)

        if params:
            query = urllib.parse.urlencode(params)
            if "?" in url:
                url += "&" + query
            else:
                url += "?" + query

        req_headers = {**self.headers}
        from . import http_retry

        response = http_retry.request_with_retries(
            method,
            url,
            host="api.github.com",
            headers=req_headers,
            timeout=self.timeout,
            max_retries=self.max_retries,
        )
        entry["status"] = response.status
        return response

    def get_all_pages(self, path, params=None, limit=None):
        all_items = []
        page = 1
        per_page = 100
        while True:
            response = self.request_raw(
                "GET", path, {**(params or {}), "page": page, "per_page": per_page}
            )
            data = response.body.decode("utf-8")
            if response.status not in (200, 201, 202, 204):
                if response.status == 404 and "billing" in path and "settings" in path:
                    raise RuntimeError(
                        f"API error 404 on billing endpoint '{path}'. "
                        f"This usually means your token does not have access "
                        f"to this billing endpoint."
                    )
                raise RuntimeError(f"API error {response.status}: {data[:200]}")

            if data:
                try:
                    result = json.loads(data)
                except json.JSONDecodeError:
                    raise RuntimeError(
                        f"API returned success {response.status} but invalid JSON: {data[:200]}"
                    ) from None
            else:
                result = {}

            if not isinstance(result, list):
                if isinstance(result, dict) and "message" in result:
                    raise RuntimeError(f"API error on {path}: {result['message']}")
                if isinstance(result, dict):
                    for key in _COLLECTION_KEYS:
                        if key in result and isinstance(result[key], list):
                            result = result[key]
                            break
                    else:
                        break  # unknown dict shape — keep prior empty-list behavior
                else:
                    break

            all_items.extend(result)
            if limit and len(all_items) >= limit:
                break
            link_header = response.headers.get("Link", "")
            if 'rel="next"' not in link_header:
                break
            page += 1
        return all_items
