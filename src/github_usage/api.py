"""GitHub REST API client for github-usage."""

from __future__ import annotations

import http.client
import json
import time


class GitHubAPI:
    def __init__(self, token):
        self.token = token
        self.base = "https://api.github.com"
        self.headers = {
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "github-usage-report-v3",
        }

    def request(self, method, path, params=None):
        url = path
        if params:
            query = "&".join(f"{k}={v}" for k, v in params.items())
            url += f"?{query}"
        conn = http.client.HTTPSConnection("api.github.com")
        req_headers = {**self.headers}
        conn.request(method, url, headers=req_headers)
        resp = conn.getresponse()
        data = resp.read().decode("utf-8")
        if resp.status in (200, 201, 202, 204):
            if data:
                try:
                    return json.loads(data)
                except json.JSONDecodeError:
                    return {}
            return {}
        elif resp.status == 403:
            try:
                body = json.loads(data) if data else {}
            except json.JSONDecodeError:
                body = {}
            reset = int(body.get("retry-after", 0) or 0)
            if reset > 0:
                time.sleep(reset + 1)
                return self.request(method, path, params)
            raise RuntimeError(f"API error 403: {data[:200]}")
        elif resp.status == 404:
            # Check if this is a billing endpoint that needs 'user' scope
            if "billing" in path and "settings" in path:
                raise RuntimeError(
                    f"API error 404 on billing endpoint '{path}'. "
                    f"This usually means your token is missing the 'user' scope. "
                    f"Fix: run 'gh auth refresh -h github.com -s user'"
                )
            raise RuntimeError(f"API error 404: {data[:200]}")
        else:
            raise RuntimeError(f"API error {resp.status}: {data[:200]}")

    def get_all_pages(self, path, params=None):
        all_items = []
        page = 1
        per_page = 100
        while True:
            result = self.request(
                "GET", path, {**(params or {}), "page": page, "per_page": per_page}
            )
            if not result:
                break
            if isinstance(result, list):
                all_items.extend(result)
                if len(result) < per_page:
                    break
                page += 1
            else:
                break
        return all_items
