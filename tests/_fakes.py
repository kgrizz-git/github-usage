"""Shared test fixtures and fakes."""

from __future__ import annotations

import subprocess

from github_usage.api import _RESOURCE_BUCKETS, _classify_request_path


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

    def get_all_pages(self, path, params=None, limit=None):
        del limit  # tests return preconfigured pages regardless of limit
        self.requests.append(("PAGES", path, params or {}))
        return self._pages_responses.get(path, [])


class CountingFakeAPI(FakeAPI):
    """FakeAPI that counts logical calls like GitHubAPI.

    Counts every ``request`` and every ``get_all_pages`` page (via
    ``page_counts`` for multi-page listings) and exposes
    ``get_request_stats()`` with the same per-resource buckets as the real
    client, so builder merge math can be tested with deterministic
    positive counts.
    """

    def __init__(self, request_responses=None, pages_responses=None, page_counts=None):
        """Optionally pass ``page_counts`` mapping a path to the number of
        paginated calls ``get_all_pages`` should record for it, modelling a
        multi-page listing against a single payload."""
        super().__init__(request_responses, pages_responses)
        self._page_counts = page_counts or {}
        self.request_count = 0
        self.request_log: list = []

    def _record(self, method, path):
        entry = {"method": method, "path": path, "status": 200}
        self.request_count += 1
        self.request_log.append(entry)
        return entry

    def request(self, method, path, params=None):
        entry = self._record(method, path)
        try:
            return super().request(method, path, params)
        except Exception:
            entry["status"] = None
            raise

    def get_all_pages(self, path, params=None, limit=None):
        # Mirror the real client's per-page counting: one log entry per page.
        for _ in range(self._page_counts.get(path, 1)):
            self._record("GET", path)
        return super().get_all_pages(path, params, limit)

    def get_request_stats(self):
        by_resource: dict[str, int] = dict.fromkeys(_RESOURCE_BUCKETS, 0)
        for entry in self.request_log:
            bucket = _classify_request_path(entry["path"])
            by_resource[bucket] = by_resource.get(bucket, 0) + 1
        return {
            "actual_requests": self.request_count,
            "actual_requests_by_resource": by_resource,
        }


class FakeGit:
    """Reusable fake of ``subprocess.run`` for ``git`` invocations in unit tests.

    Intended to be installed via ``mock.patch.object(<module>, "_run_git",
    side_effect=fake)`` (or the equivalent for whichever thin wrapper the
    module uses around ``subprocess.run``). The wrapper is what prepends
    ``"git"`` to the argv, so:

    - **Response keys** in ``responses`` are the argv list **without** the
      leading ``"git"`` element (e.g. ``("rev-parse", "--abbrev-ref", "HEAD")``,
      not ``("git", "rev-parse", "--abbrev-ref", "HEAD")``). They are
      matched in order against the recorded call; a key element may also
      be ``"*"`` to wildcard-match any argv at that position.
    - The **value** is either a dict (used to build a
      ``CompletedProcess`` via ``_make_result``) or an ``Exception`` instance
      to raise.
    - **Configured lookups** (a matching key is found) default to
      ``returncode=0`` (success).
    - **Unconfigured lookups** (no matching key) default to
      ``returncode=1`` (failure). This makes the algorithm under test fall
      through to its next fallback rather than silently succeeding.

    All calls are recorded on ``self.calls`` (a list of the argv tuples
    actually passed to the fake) so tests can assert which git commands
    were issued and in what order.
    """

    def __init__(self, responses=None, default_stdout="", default_stderr=""):
        self.responses: dict = responses or {}
        self.default_stdout = default_stdout
        self.default_stderr = default_stderr
        self.calls: list = []

    def __call__(self, args, **kwargs):
        self.calls.append(tuple(args))
        argv = tuple(args)
        for key, value in self.responses.items():
            if self._matches(key, argv):
                if isinstance(value, Exception):
                    raise value
                return self._make_result(value, matched=True)
        return self._make_result({}, matched=False)

    @staticmethod
    def _matches(key, argv):
        if len(key) > len(argv):
            return False
        return all(k == a or k == "*" for k, a in zip(key, argv, strict=False))

    def _make_result(self, spec, *, matched):
        default_rc = 0 if matched else 1
        return subprocess.CompletedProcess(
            args=[],
            returncode=spec.get("returncode", default_rc),
            stdout=spec.get("stdout", self.default_stdout),
            stderr=spec.get("stderr", self.default_stderr),
        )
