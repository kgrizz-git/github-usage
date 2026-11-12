import unittest
from unittest import mock


class ApiTests(unittest.TestCase):
    def test_request_builds_query_and_parses_json(self):
        from github_usage.api import GitHubAPI

        conn = mock.Mock()
        resp = mock.Mock(status=200)
        import http.client

        resp.headers = http.client.HTTPMessage()
        resp.read.return_value = b'{"ok": true}'
        conn.getresponse.return_value = resp

        with mock.patch("github_usage.http_retry.http.client.HTTPSConnection", return_value=conn):
            result = GitHubAPI("fake-token").request("GET", "/resource", {"b": 2, "a": 1})

        self.assertEqual(result, {"ok": True})
        conn.request.assert_called_once()
        method, url = conn.request.call_args.args[:2]
        self.assertEqual(method, "GET")
        self.assertEqual(url, "/resource?b=2&a=1")

    def test_request_returns_empty_dict_for_empty_success_body(self):
        from github_usage.api import GitHubAPI

        conn = mock.Mock()
        resp = mock.Mock(status=204)
        import http.client

        resp.headers = http.client.HTTPMessage()
        resp.read.return_value = b""
        conn.getresponse.return_value = resp

        with mock.patch("github_usage.http_retry.http.client.HTTPSConnection", return_value=conn):
            result = GitHubAPI("fake-token").request("DELETE", "/resource")

        self.assertEqual(result, {})

    def test_billing_404_message_no_longer_mentions_user_scope(self):
        from github_usage.api import GitHubAPI

        conn = mock.Mock()
        resp = mock.Mock(status=404)
        import http.client

        resp.headers = http.client.HTTPMessage()
        resp.read.return_value = b'{"message":"not found"}'
        conn.getresponse.return_value = resp

        with (
            mock.patch("github_usage.http_retry.http.client.HTTPSConnection", return_value=conn),
            self.assertRaisesRegex(RuntimeError, "does not have access"),
        ):
            GitHubAPI("fake-token").request("GET", "/users/octocat/settings/billing/usage/summary")

    def test_user_agent_includes_version_and_repo_url(self):
        from github_usage import __version__
        from github_usage.api import GitHubAPI

        api = GitHubAPI("fake-token")

        self.assertIn(f"github-usage-report/{__version__}", api.headers["User-Agent"])
        self.assertIn("github.com", api.headers["User-Agent"])

    def test_request_retries_on_403_with_retry_after(self):
        from github_usage.api import GitHubAPI

        conn = mock.Mock()
        resp_403 = mock.Mock(status=403)
        import http.client

        resp_403.headers = http.client.HTTPMessage()
        resp_403.headers["Retry-After"] = "1"
        resp_403.read.return_value = b'{"message": "rate limit"}'

        resp_200 = mock.Mock(status=200)
        resp_200.headers = http.client.HTTPMessage()
        resp_200.read.return_value = b'{"ok": true}'

        conn.getresponse.side_effect = [resp_403, resp_200]

        with (
            mock.patch("github_usage.http_retry.http.client.HTTPSConnection", return_value=conn),
            mock.patch("github_usage.http_retry.time.sleep") as sleep,
        ):
            result = GitHubAPI("fake-token").request("GET", "/resource")

        self.assertEqual(result, {"ok": True})
        self.assertEqual(conn.request.call_count, 2)
        sleep.assert_called_once_with(1.0)

    def test_request_encodes_query_params_safely(self):
        from github_usage.api import GitHubAPI

        conn = mock.Mock()
        resp = mock.Mock(status=200)
        import http.client

        resp.headers = http.client.HTTPMessage()
        resp.read.return_value = b'{"ok": true}'
        conn.getresponse.return_value = resp

        with mock.patch("github_usage.http_retry.http.client.HTTPSConnection", return_value=conn):
            # Test with special characters and path without leading slash
            GitHubAPI("fake-token").request("GET", "resource", {"q": "a+b&c=d"})

        conn.request.assert_called_once()
        _, url = conn.request.call_args.args[:2]
        self.assertEqual(url, "/resource?q=a%2Bb%26c%3Dd")

    def test_get_all_pages_uses_link_header(self):
        from github_usage.api import GitHubAPI

        api = GitHubAPI("fake-token")

        # Mock request to return Response objects
        def mock_request_raw(method, path, params=None):
            import http.client

            from github_usage.http_retry import Response

            headers = http.client.HTTPMessage()
            if params.get("page") == 1:  # type: ignore[union-attr]
                headers["Link"] = '<https://api.github.com/resource?page=2>; rel="next"'
                return Response(status=200, body=b'[{"id": 1}]', headers=headers)
            else:
                return Response(status=200, body=b'[{"id": 2}]', headers=headers)

        with mock.patch.object(api, "request_raw", side_effect=mock_request_raw):
            result = api.get_all_pages("/resource")

        self.assertEqual(result, [{"id": 1}, {"id": 2}])

    def test_get_all_pages_stops_early_when_limit_reached(self):
        # Fix #3: a limit parameter stops pagination once enough items are collected.
        from github_usage.api import GitHubAPI

        api = GitHubAPI("fake-token")
        call_count = 0

        def mock_request_raw(method, path, params=None):
            import http.client

            from github_usage.http_retry import Response

            nonlocal call_count
            call_count += 1
            headers = http.client.HTTPMessage()
            # Always advertise a next page so the loop would run forever without limit
            headers["Link"] = (
                f'<https://api.github.com/resource?page={params["page"] + 1}>; rel="next"'  # type: ignore[index]
            )
            items = [{"id": params["page"]}]  # type: ignore[index]
            return Response(
                status=200, body=__import__("json").dumps(items).encode(), headers=headers
            )

        with mock.patch.object(api, "request_raw", side_effect=mock_request_raw):
            result = api.get_all_pages("/resource", limit=2)

        self.assertEqual(len(result), 2)
        self.assertEqual(call_count, 2)

    def test_get_all_pages_unwraps_workflow_runs_and_follows_next(self):
        """Object-shaped {workflow_runs: [...]} responses are unwrapped and paginated."""
        import json

        from github_usage.api import GitHubAPI
        from github_usage.http_retry import Response

        api = GitHubAPI("fake-token")

        def mock_request_raw(method, path, params=None):
            import http.client

            headers = http.client.HTTPMessage()
            page = params.get("page")  # type: ignore[union-attr]
            if page == 1:
                headers["Link"] = '<https://api.github.com/runs?page=2>; rel="next"'
                body = json.dumps(
                    {"total_count": 2, "workflow_runs": [{"id": 1, "name": "CI"}]}
                ).encode()
            else:
                body = json.dumps(
                    {"total_count": 2, "workflow_runs": [{"id": 2, "name": "Deploy"}]}
                ).encode()
            return Response(status=200, body=body, headers=headers)

        with mock.patch.object(api, "request_raw", side_effect=mock_request_raw):
            result = api.get_all_pages("/repos/octocat/api/actions/runs")

        self.assertEqual(result, [{"id": 1, "name": "CI"}, {"id": 2, "name": "Deploy"}])

    def test_get_all_pages_unwraps_artifacts_and_workflows(self):
        """Recognized collection keys artifacts and workflows are also unwrapped."""
        import json

        from github_usage.api import GitHubAPI
        from github_usage.http_retry import Response

        api = GitHubAPI("fake-token")

        def mock_request_raw(method, path, params=None):
            import http.client

            headers = http.client.HTTPMessage()
            if "artifacts" in path:
                body = json.dumps(
                    {"total_count": 1, "artifacts": [{"id": 10, "size_in_bytes": 512}]}
                ).encode()
            else:
                body = json.dumps(
                    {"total_count": 1, "workflows": [{"id": 20, "name": "CI"}]}
                ).encode()
            return Response(status=200, body=body, headers=headers)

        with mock.patch.object(api, "request_raw", side_effect=mock_request_raw):
            artifacts = api.get_all_pages("/repos/octocat/api/actions/artifacts")
            workflows = api.get_all_pages("/repos/octocat/api/actions/workflows")

        self.assertEqual(artifacts, [{"id": 10, "size_in_bytes": 512}])
        self.assertEqual(workflows, [{"id": 20, "name": "CI"}])

    def test_get_all_pages_unknown_dict_shape_returns_empty(self):
        """Unknown dict shapes still break without raising (current behavior)."""
        import json

        from github_usage.api import GitHubAPI
        from github_usage.http_retry import Response

        api = GitHubAPI("fake-token")

        def mock_request_raw(method, path, params=None):
            import http.client

            headers = http.client.HTTPMessage()
            body = json.dumps({"total_count": 1, "items": [{"id": 1}]}).encode()
            return Response(status=200, body=body, headers=headers)

        with mock.patch.object(api, "request_raw", side_effect=mock_request_raw):
            result = api.get_all_pages("/unknown")

        self.assertEqual(result, [])

    def test_get_all_pages_null_collection_does_not_raise(self):
        """Null collection values (e.g. workflow_runs: null) must not raise."""
        import json

        from github_usage.api import GitHubAPI
        from github_usage.http_retry import Response

        api = GitHubAPI("fake-token")

        def mock_request_raw(method, path, params=None):
            import http.client

            headers = http.client.HTTPMessage()
            body = json.dumps({"total_count": 0, "workflow_runs": None}).encode()
            return Response(status=200, body=body, headers=headers)

        with mock.patch.object(api, "request_raw", side_effect=mock_request_raw):
            result = api.get_all_pages("/repos/octocat/api/actions/runs")

        self.assertEqual(result, [])


class RequestCountingTests(unittest.TestCase):
    """request_count / request_log / get_request_stats on GitHubAPI."""

    def _conn(self, status=200, body=b"{}"):
        import http.client

        conn = mock.Mock()
        resp = mock.Mock(status=status)
        resp.headers = http.client.HTTPMessage()
        resp.read.return_value = body
        conn.getresponse.return_value = resp
        return conn

    def test_request_counts_and_logs_success(self):
        from github_usage.api import GitHubAPI

        api = GitHubAPI("fake-token")
        with mock.patch(
            "github_usage.http_retry.http.client.HTTPSConnection",
            return_value=self._conn(),
        ):
            api.request("GET", "/user")
            api.request("GET", "/meta")

        self.assertEqual(api.request_count, 2)
        self.assertEqual(
            [(e["method"], e["path"], e["status"]) for e in api.request_log],
            [("GET", "/user", 200), ("GET", "/meta", 200)],
        )
        stats = api.get_request_stats()
        self.assertEqual(stats["actual_requests"], 2)
        self.assertEqual(stats["actual_requests_by_resource"]["user"], 1)
        self.assertEqual(stats["actual_requests_by_resource"]["other"], 1)
        self.assertEqual(
            sum(stats["actual_requests_by_resource"].values()), stats["actual_requests"]
        )

    def test_not_found_records_status(self):
        from github_usage.api import GitHubAPI

        api = GitHubAPI("fake-token")
        with (
            mock.patch(
                "github_usage.http_retry.http.client.HTTPSConnection",
                return_value=self._conn(status=404, body=b'{"message": "nope"}'),
            ),
            self.assertRaisesRegex(RuntimeError, "API error 404"),
        ):
            api.request("GET", "/user")

        self.assertEqual(api.request_count, 1)
        self.assertEqual(api.request_log[0]["status"], 404)

    def test_logged_path_is_normalized_and_excludes_query_params(self):
        from github_usage.api import GitHubAPI

        api = GitHubAPI("fake-token")
        with mock.patch(
            "github_usage.http_retry.http.client.HTTPSConnection",
            return_value=self._conn(),
        ):
            api.request("GET", "user", {"page": 1, "per_page": 100})

        entry = api.request_log[0]
        self.assertEqual(entry["method"], "GET")
        self.assertEqual(entry["path"], "/user")
        self.assertEqual(api.get_request_stats()["actual_requests_by_resource"]["user"], 1)

    def test_failed_request_still_counts_with_response_status(self):
        from github_usage.api import GitHubAPI

        api = GitHubAPI("fake-token")
        with (
            mock.patch(
                "github_usage.http_retry.http.client.HTTPSConnection",
                return_value=self._conn(status=403, body=b'{"message": "x"}'),
            ),
            self.assertRaisesRegex(RuntimeError, "API error 403"),
        ):
            api.request("GET", "/user")

        self.assertEqual(api.request_count, 1)
        self.assertEqual(api.request_log[0]["status"], 403)
        stats = api.get_request_stats()
        self.assertEqual(stats["actual_requests"], 1)
        self.assertEqual(sum(stats["actual_requests_by_resource"].values()), 1)

    def test_transport_failure_keeps_none_status_but_still_counts(self):
        from github_usage.api import GitHubAPI

        api = GitHubAPI("fake-token")
        with (
            mock.patch(
                "github_usage.http_retry.request_with_retries",
                side_effect=RuntimeError("boom"),
            ),
            self.assertRaisesRegex(RuntimeError, "boom"),
        ):
            api.request("GET", "/user")

        self.assertEqual(api.request_count, 1)
        self.assertIsNone(api.request_log[0]["status"])
        self.assertEqual(api.get_request_stats()["actual_requests"], 1)

    def test_request_raw_counts_each_call(self):
        from github_usage.api import GitHubAPI

        api = GitHubAPI("fake-token")
        with mock.patch(
            "github_usage.http_retry.http.client.HTTPSConnection",
            return_value=self._conn(),
        ):
            api.request_raw("GET", "/user")
            api.request_raw("GET", "/rate_limit")

        self.assertEqual(api.request_count, 2)
        self.assertEqual(
            api.get_request_stats()["actual_requests_by_resource"],
            {"billing": 0, "user": 1, "rate_limit": 1, "actions": 0, "repos": 0, "other": 0},
        )

    def test_get_all_pages_counts_each_page(self):
        import http.client

        from github_usage.api import GitHubAPI

        api = GitHubAPI("fake-token")
        first = http.client.HTTPMessage()
        first["Link"] = '<https://api.github.com/resource?page=2>; rel="next"'
        conn = mock.Mock()
        resp1 = mock.Mock(status=200)
        resp1.headers = first
        resp1.read.return_value = b'[{"id": 1}]'
        resp2 = mock.Mock(status=200)
        resp2.headers = http.client.HTTPMessage()
        resp2.read.return_value = b'[{"id": 2}]'
        conn.getresponse.side_effect = [resp1, resp2]

        with mock.patch("github_usage.http_retry.http.client.HTTPSConnection", return_value=conn):
            result = api.get_all_pages("/resource")

        self.assertEqual(result, [{"id": 1}, {"id": 2}])
        self.assertEqual(api.request_count, 2)

    def test_get_request_stats_classifies_paths_into_buckets(self):
        from github_usage.api import GitHubAPI

        api = GitHubAPI("fake-token")
        paths = [
            "/user",
            "/user/repos",
            "/user/repos/octocat",
            "/rate_limit",
            "/users/octocat/settings/billing/usage/summary",
            "/repos/octocat/repo/actions/artifacts",
            "/repos/octocat/repo/releases",
            "/meta",
        ]
        with mock.patch(
            "github_usage.http_retry.http.client.HTTPSConnection",
            return_value=self._conn(),
        ):
            for path in paths:
                api.request("GET", path)

        stats = api.get_request_stats()
        self.assertEqual(stats["actual_requests"], 8)
        # Billing lives under /users/ but buckets by its /settings/billing/
        # segment; the billing branch stays first as defensive ordering.
        # The repository listing (/user/repos, incl. sub-paths) buckets as
        # repos, not user.
        self.assertEqual(
            stats["actual_requests_by_resource"],
            {
                "user": 1,
                "rate_limit": 1,
                "billing": 1,
                "actions": 1,
                "repos": 3,
                "other": 1,
            },
        )
        self.assertEqual(
            sum(stats["actual_requests_by_resource"].values()), stats["actual_requests"]
        )

    def test_stats_start_at_zero_for_fresh_client(self):
        from github_usage.api import GitHubAPI

        stats = GitHubAPI("fake-token").get_request_stats()
        self.assertEqual(stats["actual_requests"], 0)
        self.assertEqual(
            stats["actual_requests_by_resource"],
            {
                "billing": 0,
                "user": 0,
                "rate_limit": 0,
                "actions": 0,
                "repos": 0,
                "other": 0,
            },
        )
