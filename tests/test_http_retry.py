import http.client
import unittest
from unittest import mock

from github_usage import http_retry
from tests._fakes import FakeSleeper, assert_monotonic_increasing


class HttpRetryTests(unittest.TestCase):
    def setUp(self):
        self.sleeper = FakeSleeper()

    @mock.patch("http.client.HTTPSConnection")
    def test_retries_on_5xx_then_succeeds(self, mock_conn_class):
        conn = mock.Mock()
        mock_conn_class.return_value = conn

        err_resp = mock.Mock(status=500, headers=http.client.HTTPMessage())
        err_resp.read.return_value = b"Error"
        succ_resp = mock.Mock(status=200, headers=http.client.HTTPMessage())
        succ_resp.read.return_value = b"Success"

        conn.getresponse.side_effect = [err_resp, err_resp, succ_resp]

        response = http_retry.request_with_retries(
            "GET", "/foo", host="api.github.com", headers={}, sleep=self.sleeper
        )
        self.assertEqual(response.status, 200)
        self.assertEqual(response.body, b"Success")
        self.assertEqual(len(self.sleeper.calls), 2)
        assert_monotonic_increasing(self.sleeper.calls)
        self.assertEqual(conn.request.call_count, 3)

    @mock.patch("http.client.HTTPSConnection")
    def test_respects_retry_after_header(self, mock_conn_class):
        conn = mock.Mock()
        mock_conn_class.return_value = conn

        headers = http.client.HTTPMessage()
        headers["Retry-After"] = "7"
        err_resp = mock.Mock(status=503, headers=headers)
        err_resp.read.return_value = b"Service Unavailable"
        succ_resp = mock.Mock(status=200, headers=http.client.HTTPMessage())
        succ_resp.read.return_value = b"Success"

        conn.getresponse.side_effect = [err_resp, succ_resp]

        http_retry.request_with_retries(
            "GET", "/foo", host="api.github.com", headers={}, sleep=self.sleeper
        )
        self.assertEqual(self.sleeper.calls, [7.0])

    @mock.patch("time.time", return_value=1000000.0)
    @mock.patch("http.client.HTTPSConnection")
    def test_respects_x_ratelimit_reset(self, mock_conn_class, mock_time):
        conn = mock.Mock()
        mock_conn_class.return_value = conn

        headers = http.client.HTTPMessage()
        headers["x-ratelimit-reset"] = "1000005.0"
        err_resp = mock.Mock(status=403, headers=headers)
        err_resp.read.return_value = b"Rate limit exceeded"
        succ_resp = mock.Mock(status=200, headers=http.client.HTTPMessage())
        succ_resp.read.return_value = b"Success"

        conn.getresponse.side_effect = [err_resp, succ_resp]

        http_retry.request_with_retries(
            "GET", "/foo", host="api.github.com", headers={}, sleep=self.sleeper
        )
        self.assertEqual(self.sleeper.calls, [5.0])

    @mock.patch("http.client.HTTPSConnection")
    def test_does_not_retry_on_404(self, mock_conn_class):
        conn = mock.Mock()
        mock_conn_class.return_value = conn

        err_resp = mock.Mock(status=404, headers=http.client.HTTPMessage())
        err_resp.read.return_value = b"Not Found"
        conn.getresponse.return_value = err_resp

        response = http_retry.request_with_retries(
            "GET", "/foo", host="api.github.com", headers={}, sleep=self.sleeper
        )
        self.assertEqual(response.status, 404)
        self.assertEqual(self.sleeper.calls, [])
        self.assertEqual(conn.request.call_count, 1)

    @mock.patch("http.client.HTTPSConnection")
    def test_does_not_retry_on_401_and_headerless_403(self, mock_conn_class):
        conn = mock.Mock()
        mock_conn_class.return_value = conn

        err_resp = mock.Mock(status=401, headers=http.client.HTTPMessage())
        err_resp.read.return_value = b"Unauthorized"
        conn.getresponse.return_value = err_resp

        response = http_retry.request_with_retries(
            "GET", "/foo", host="api.github.com", headers={}, sleep=self.sleeper
        )
        self.assertEqual(response.status, 401)
        self.assertEqual(conn.request.call_count, 1)

        err_resp2 = mock.Mock(status=403, headers=http.client.HTTPMessage())
        err_resp2.read.return_value = b"Forbidden"
        conn.getresponse.return_value = err_resp2
        response2 = http_retry.request_with_retries(
            "GET", "/foo", host="api.github.com", headers={}, sleep=self.sleeper
        )
        self.assertEqual(response2.status, 403)
        self.assertEqual(conn.request.call_count, 2)
        self.assertEqual(self.sleeper.calls, [])

    @mock.patch("http.client.HTTPSConnection")
    def test_retries_on_remote_disconnected(self, mock_conn_class):
        conn = mock.Mock()
        mock_conn_class.return_value = conn

        succ_resp = mock.Mock(status=200, headers=http.client.HTTPMessage())
        succ_resp.read.return_value = b"Success"

        conn.request.side_effect = [http.client.RemoteDisconnected("Disconnected"), None]
        conn.getresponse.return_value = succ_resp

        response = http_retry.request_with_retries(
            "GET", "/foo", host="api.github.com", headers={}, sleep=self.sleeper
        )
        self.assertEqual(response.status, 200)
        self.assertEqual(conn.request.call_count, 2)
        self.assertEqual(len(self.sleeper.calls), 1)

    @mock.patch("http.client.HTTPSConnection")
    def test_exhausts_retries_then_raises_runtime_error(self, mock_conn_class):
        conn = mock.Mock()
        mock_conn_class.return_value = conn

        err_resp = mock.Mock(status=500, headers=http.client.HTTPMessage())
        err_resp.read.return_value = b"Internal Server Error"
        conn.getresponse.return_value = err_resp

        with self.assertRaises(RuntimeError) as cm:
            http_retry.request_with_retries(
                "GET", "/foo", host="api.github.com", headers={}, max_retries=3, sleep=self.sleeper
            )
        self.assertIn("API error 500", str(cm.exception))
        self.assertEqual(conn.request.call_count, 4)

    def test_timeout_zero_translates_to_blocking(self):
        with mock.patch("http.client.HTTPSConnection") as mock_conn_class:
            conn = mock.Mock()
            mock_conn_class.return_value = conn
            succ_resp = mock.Mock(status=200, headers=http.client.HTTPMessage())
            succ_resp.read.return_value = b"Success"
            conn.getresponse.return_value = succ_resp

            http_retry.request_with_retries(
                "GET", "/foo", host="api.github.com", headers={}, timeout=0, sleep=self.sleeper
            )
            mock_conn_class.assert_called_with("api.github.com", timeout=None)

    def test_negative_timeout_raises(self):
        with self.assertRaises(ValueError):
            http_retry.request_with_retries(
                "GET", "/foo", host="api.github.com", headers={}, timeout=-1.0, sleep=self.sleeper
            )

    @mock.patch("http.client.HTTPSConnection")
    def test_max_retries_zero_means_no_retry(self, mock_conn_class):
        conn = mock.Mock()
        mock_conn_class.return_value = conn

        err_resp = mock.Mock(status=500, headers=http.client.HTTPMessage())
        err_resp.read.return_value = b"Error"
        conn.getresponse.return_value = err_resp

        with self.assertRaises(RuntimeError):
            http_retry.request_with_retries(
                "GET", "/foo", host="api.github.com", headers={}, max_retries=0, sleep=self.sleeper
            )
        self.assertEqual(conn.request.call_count, 1)

    @mock.patch("time.time", return_value=1000000.0)
    def test_parse_rate_limit_headers(self, mock_time):
        headers = http.client.HTTPMessage()

        # Missing
        self.assertIsNone(http_retry.parse_rate_limit_headers(headers))

        # Retry-After int
        headers["Retry-After"] = "15"
        self.assertEqual(http_retry.parse_rate_limit_headers(headers), 15.0)

        # Retry-After date
        del headers["Retry-After"]
        # Wed, 21 Oct 2015 07:28:00 GMT -> 1445412480.0
        # If time is 1445412470.0, diff is 10.
        with mock.patch("time.time", return_value=1445412470.0):
            headers["Retry-After"] = "Wed, 21 Oct 2015 07:28:00 GMT"
            self.assertEqual(http_retry.parse_rate_limit_headers(headers), 10.0)

        del headers["Retry-After"]

        # x-ratelimit-reset
        headers["x-ratelimit-reset"] = "1000010"
        self.assertEqual(http_retry.parse_rate_limit_headers(headers), 10.0)

        del headers["x-ratelimit-reset"]
        headers["x-ratelimit-reset"] = "invalid"
        self.assertIsNone(http_retry.parse_rate_limit_headers(headers))


if __name__ == "__main__":
    unittest.main()
