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
