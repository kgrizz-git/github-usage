"""Shared test fixtures and fakes."""

from __future__ import annotations


class FakeSleeper:
    def __init__(self):
        self.calls: list[float] = []

    def __call__(self, seconds: float) -> None:
        self.calls.append(seconds)


def assert_monotonic_increasing(calls: list[float]) -> None:
    for i in range(1, len(calls)):
        assert calls[i] >= calls[i - 1], f"Not monotonic increasing: {calls}"


class FakeAPI:
    """Reusable fake GitHub API client for unit tests.

    Configures mock responses for ``request`` and ``get_all_pages``
    independently via the ``request_responses`` and ``pages_responses``
    arguments. Both default to empty mappings so call sites that only need
    one of the two methods do not have to set up the other.

    ``request_responses`` keys are ``(method, path, sorted_params_tuple)``;
    the value is the response to return, or an ``Exception`` instance to
    raise. Unconfigured lookups return ``None``.

    ``pages_responses`` keys are paths; the value is a list to return from
    ``get_all_pages``. Unconfigured lookups return ``[]``.

    All calls are recorded on ``self.requests`` (a list of
    ``(method, path, params)`` for ``request`` and ``("PAGES", path, params)``
    for ``get_all_pages``) so tests can assert which endpoints were hit.
    """

    def __init__(self, request_responses=None, pages_responses=None):
        self._request_responses = request_responses or {}
        self._pages_responses = pages_responses or {}
        self.requests: list = []

    def request(self, method, path, params=None):
        self.requests.append((method, path, params or {}))
        key = (method, path, tuple(sorted((params or {}).items())))
        value = self._request_responses.get(key)
        if isinstance(value, Exception):
            raise value
        return value

    def get_all_pages(self, path, params=None):
        self.requests.append(("PAGES", path, params or {}))
        return self._pages_responses.get(path, [])
