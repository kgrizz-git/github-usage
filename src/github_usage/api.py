"""GitHub REST API client for github-usage."""

from __future__ import annotations

import http.client
import json
import time
import urllib.parse

from . import __version__


class GitHubAPI:
    def __init__(self, token):
        self.token = token
        self.base = "https://api.github.com"
        self.headers = {
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": f"github-usage-report/{__version__} (+https://github.com/kgrizz-git/github-usage)",
        }

    def request(self, method, path, params=None, _retries=0):
        url = path
        if not url.startswith("/"):
            url = "/" + url

        if params:
            query = urllib.parse.urlencode(params)
            if "?" in url:
                url += "&" + query
            else:
                url += "?" + query

        conn = http.client.HTTPSConnection("api.github.com")
        try:
            req_headers = {**self.headers}
            conn.request(method, url, headers=req_headers)
            resp = conn.getresponse()
            self._last_link = resp.getheader("Link", "")
            data = resp.read().decode("utf-8")
            if resp.status in (200, 201, 202, 204):
                if data:
                    try:
                        return json.loads(data)
                    except json.JSONDecodeError:
                        raise RuntimeError(
                            f"API returned success {resp.status} but invalid JSON: {data[:200]}"
                        ) from None
                return {}
            elif resp.status == 403:
                reset = int(resp.getheader("Retry-After", 0) or 0)
                if reset > 0 and _retries < 3:
                    time.sleep(reset + 1)
                    return self.request(method, path, params, _retries=_retries + 1)
                raise RuntimeError(f"API error 403: {data[:200]}")
            elif resp.status == 404:
                # Check if this is a billing endpoint that needs elevated access
                if "billing" in path and "settings" in path:
                    raise RuntimeError(
                        f"API error 404 on billing endpoint '{path}'. "
                        f"This usually means your token does not have access "
                        f"to this billing endpoint."
                    )
                raise RuntimeError(f"API error 404: {data[:200]}")
            else:
                raise RuntimeError(f"API error {resp.status}: {data[:200]}")
        finally:
            conn.close()

    def get_all_pages(self, path, params=None):
        all_items = []
        page = 1
        per_page = 100
        while True:
            result = self.request(
                "GET", path, {**(params or {}), "page": page, "per_page": per_page}
            )
            if not isinstance(result, list):
                if isinstance(result, dict) and "message" in result:
                    raise RuntimeError(f"API error on {path}: {result['message']}")
                break

            all_items.extend(result)
            if 'rel="next"' not in self._last_link:
                break
            page += 1
        return all_items
