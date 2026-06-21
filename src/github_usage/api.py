"""GitHub REST API client for github-usage."""

from __future__ import annotations

import json
import urllib.parse

from . import __version__


class GitHubAPI:
    def __init__(self, token, timeout=None, max_retries=None):
        from . import http_retry

        self.token = token
        self.timeout = timeout if timeout is not None else http_retry.DEFAULT_TIMEOUT_SECONDS
        self.max_retries = (
            max_retries if max_retries is not None else http_retry.DEFAULT_MAX_RETRIES
        )
        self.base = "https://api.github.com"
        self.headers = {
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": f"github-usage-report/{__version__} (+https://github.com/kgrizz-git/github-usage)",
        }

    def request(self, method, path, params=None):
        url = path
        if not url.startswith("/"):
            url = "/" + url

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

        if params:
            query = urllib.parse.urlencode(params)
            if "?" in url:
                url += "&" + query
            else:
                url += "?" + query

        req_headers = {**self.headers}
        from . import http_retry

        return http_retry.request_with_retries(
            method,
            url,
            host="api.github.com",
            headers=req_headers,
            timeout=self.timeout,
            max_retries=self.max_retries,
        )

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
                break

            all_items.extend(result)
            if limit and len(all_items) >= limit:
                break
            link_header = response.headers.get("Link", "")
            if 'rel="next"' not in link_header:
                break
            page += 1
        return all_items
