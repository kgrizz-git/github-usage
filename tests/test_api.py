import unittest
from unittest import mock


class ApiTests(unittest.TestCase):
    def test_request_builds_query_and_parses_json(self):
        from github_usage.api import GitHubAPI

        conn = mock.Mock()
        resp = mock.Mock(status=200)
        resp.read.return_value = b'{"ok": true}'
        conn.getresponse.return_value = resp

        with mock.patch("github_usage.api.http.client.HTTPSConnection", return_value=conn):
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
        resp.read.return_value = b""
        conn.getresponse.return_value = resp

        with mock.patch("github_usage.api.http.client.HTTPSConnection", return_value=conn):
            result = GitHubAPI("fake-token").request("DELETE", "/resource")

        self.assertEqual(result, {})

    def test_billing_404_message_no_longer_mentions_user_scope(self):
        from github_usage.api import GitHubAPI

        conn = mock.Mock()
        resp = mock.Mock(status=404)
        resp.read.return_value = b'{"message":"not found"}'
        conn.getresponse.return_value = resp

        with (
            mock.patch("github_usage.api.http.client.HTTPSConnection", return_value=conn),
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
        resp_403.getheader.return_value = "1"
        resp_403.read.return_value = b'{"message": "rate limit"}'

        resp_200 = mock.Mock(status=200)
        resp_200.read.return_value = b'{"ok": true}'

        conn.getresponse.side_effect = [resp_403, resp_200]

        with (
            mock.patch("github_usage.api.http.client.HTTPSConnection", return_value=conn),
            mock.patch("github_usage.api.time.sleep") as sleep,
        ):
            result = GitHubAPI("fake-token").request("GET", "/resource")

        self.assertEqual(result, {"ok": True})
        self.assertEqual(conn.request.call_count, 2)
        sleep.assert_called_once_with(2)

    def test_request_encodes_query_params_safely(self):
        from github_usage.api import GitHubAPI

        conn = mock.Mock()
        resp = mock.Mock(status=200)
        resp.read.return_value = b'{"ok": true}'
        conn.getresponse.return_value = resp

        with mock.patch("github_usage.api.http.client.HTTPSConnection", return_value=conn):
            # Test with special characters and path without leading slash
            GitHubAPI("fake-token").request("GET", "resource", {"q": "a+b&c=d"})

        conn.request.assert_called_once()
        _, url = conn.request.call_args.args[:2]
        self.assertEqual(url, "/resource?q=a%2Bb%26c%3Dd")

    def test_get_all_pages_uses_link_header(self):
        from github_usage.api import GitHubAPI

        api = GitHubAPI("fake-token")

        # Mock request to return headers
        def mock_request(method, path, params=None, _retries=0):
            if params.get("page") == 1:
                api._last_link = '<https://api.github.com/resource?page=2>; rel="next"'
                return [{"id": 1}]
            else:
                api._last_link = ""
                return [{"id": 2}]

        with mock.patch.object(api, "request", side_effect=mock_request):
            result = api.get_all_pages("/resource")

        self.assertEqual(result, [{"id": 1}, {"id": 2}])
