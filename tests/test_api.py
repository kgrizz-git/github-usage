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

    def test_billing_404_includes_user_scope_guidance(self):
        from github_usage.api import GitHubAPI

        conn = mock.Mock()
        resp = mock.Mock(status=404)
        resp.read.return_value = b'{"message":"not found"}'
        conn.getresponse.return_value = resp

        with (
            mock.patch("github_usage.api.http.client.HTTPSConnection", return_value=conn),
            self.assertRaisesRegex(RuntimeError, "missing the 'user' scope"),
        ):
            GitHubAPI("fake-token").request("GET", "/users/octocat/settings/billing/usage/summary")
