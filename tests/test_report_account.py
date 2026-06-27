import unittest
from contextlib import redirect_stdout
from io import StringIO

from tests._fakes import FakeAPI


class AccountReportTests(unittest.TestCase):
    def test_show_account_info_prints_user_login(self):
        from github_usage.report_account import show_account_info

        api = FakeAPI(
            request_responses={
                ("GET", "/user", ()): {"login": "octocat", "type": "User", "plan": {"name": "free"}}
            }
        )

        stdout = StringIO()
        with redirect_stdout(stdout):
            username, user_type = show_account_info(api)

        self.assertEqual(username, "octocat")
        self.assertEqual(user_type, "User")
        self.assertIn("Username:   octocat", stdout.getvalue())
        self.assertIn("Account:    User", stdout.getvalue())

    def test_show_account_info_prints_pro_plan_happy_path(self):
        """Baseline: plan populated with name, space, collaborators, private_repos.

        Establishes coverage so the isinstance guards added below are not the
        only test of this function.
        """
        from github_usage.report_account import show_account_info

        api = FakeAPI(
            request_responses={
                ("GET", "/user", ()): {
                    "login": "octocat",
                    "type": "User",
                    "plan": {
                        "name": "pro",
                        "space": 2 * 1024 * 1024 * 1024,  # 2 GB in bytes
                        "collaborators": 10,
                        "private_repos": 50,
                    },
                }
            }
        )

        stdout = StringIO()
        with redirect_stdout(stdout):
            show_account_info(api)

        output = stdout.getvalue()
        self.assertIn("Plan:       pro", output)
        self.assertIn("Space:      2.0 GB available", output)
        self.assertIn("Collaborators: 10", output)
        self.assertIn("Private repos: 50 allowed", output)

    def test_show_account_info_returns_username_and_type(self):
        from github_usage.report_account import show_account_info

        api = FakeAPI(
            request_responses={("GET", "/user", ()): {"login": "octocat", "type": "User"}}
        )

        stdout = StringIO()
        with redirect_stdout(stdout):
            username, user_type = show_account_info(api)

        self.assertEqual(username, "octocat")
        self.assertEqual(user_type, "User")

    def test_show_account_info_handles_non_dict_user_response(self):
        from github_usage.report_account import show_account_info

        api = FakeAPI(request_responses={("GET", "/user", ()): None})

        stdout = StringIO()
        with redirect_stdout(stdout):
            username, user_type = show_account_info(api)

        self.assertEqual(username, "?")
        self.assertEqual(user_type, "?")
        self.assertIn("Username:   ?", stdout.getvalue())

    def test_show_account_info_handles_non_dict_plan(self):
        """plan mapped to None or a non-dict must be coerced to {}; the plan block is skipped."""
        from github_usage.report_account import show_account_info

        api = FakeAPI(request_responses={("GET", "/user", ()): {"login": "octocat", "plan": None}})

        stdout = StringIO()
        with redirect_stdout(stdout):
            username, user_type = show_account_info(api)

        self.assertEqual(username, "octocat")
        self.assertIn("Username:   octocat", stdout.getvalue())
        # Plan block was skipped
        self.assertNotIn("Plan:", stdout.getvalue())

    def test_show_account_info_handles_plan_as_string(self):
        """plan mapped to a non-dict (e.g. "free") must not crash on plan.get()."""
        from github_usage.report_account import show_account_info

        api = FakeAPI(
            request_responses={("GET", "/user", ()): {"login": "octocat", "plan": "free"}}
        )

        stdout = StringIO()
        with redirect_stdout(stdout):
            username, user_type = show_account_info(api)

        self.assertEqual(username, "octocat")
        self.assertNotIn("Plan:", stdout.getvalue())

    def test_show_rate_limits_handles_non_dict_response(self):
        from github_usage.report_account import show_rate_limits

        api = FakeAPI(request_responses={("GET", "/rate_limit", ()): None})

        stdout = StringIO()
        with redirect_stdout(stdout):
            show_rate_limits(api)

        output = stdout.getvalue()
        # No raise; standard tier still iterates 4 names but values are "?"
        self.assertIn("API Rate Limit", output)
        self.assertIn("Core API", output)
        # The format is "{rem:>6} / {lim:<6}" so for "?" each side gets padded.
        # We assert that the "? / ?" pattern appears (3 standard tier lines + search/scan
        # when they hit the same fallback).
        self.assertIn("? / ?", output)

    def test_show_rate_limits_handles_non_dict_resources(self):
        """resources mapped to null or a non-dict is coerced to {}."""
        from github_usage.report_account import show_rate_limits

        api = FakeAPI(request_responses={("GET", "/rate_limit", ()): {"resources": None}})

        stdout = StringIO()
        with redirect_stdout(stdout):
            show_rate_limits(api)

        output = stdout.getvalue()
        self.assertIn("Core API", output)
        self.assertIn("? / ?", output)

    def test_show_rate_limits_handles_non_dict_resource_entry(self):
        """A standard-tier resource key mapped to None is coerced to {}; prints '?'."""
        from github_usage.report_account import show_rate_limits

        api = FakeAPI(
            request_responses={
                ("GET", "/rate_limit", ()): {
                    "resources": {
                        "core": None,
                        "graphql": {"limit": 5000, "remaining": 4500},
                    }
                }
            }
        )

        stdout = StringIO()
        with redirect_stdout(stdout):
            show_rate_limits(api)

        output = stdout.getvalue()
        # core should print ? for both remaining and limit
        self.assertIn("Core API", output)
        self.assertIn("? / ?", output)
        # graphql should print actual numbers
        self.assertIn("GraphQL API", output)
        self.assertIn("4500", output)

    def test_show_rate_limits_handles_non_dict_premium_entry(self):
        """A premium-tier resource value that is None or non-dict is skipped."""
        from github_usage.report_account import show_rate_limits

        api = FakeAPI(
            request_responses={
                ("GET", "/rate_limit", ()): {
                    "resources": {
                        "core": {"limit": 5000, "remaining": 4500},
                        "core_enterprise_tier": None,  # non-dict value
                        "actions_runner_registration": "junk",  # non-dict value
                    }
                }
            }
        )

        stdout = StringIO()
        with redirect_stdout(stdout):
            show_rate_limits(api)

        # No raise; standard tier still works.
        self.assertIn("Core API", stdout.getvalue())

    def test_show_rate_limits_formats_standard_resources(self):
        from github_usage.report_account import show_rate_limits

        api = FakeAPI(
            request_responses={
                ("GET", "/rate_limit", ()): {
                    "resources": {
                        "core": {"limit": 5000, "remaining": 4999, "used": 1, "reset": 1700000000},
                        "graphql": {"limit": 5000, "remaining": 5000, "used": 0, "reset": 0},
                    }
                }
            }
        )

        stdout = StringIO()
        with redirect_stdout(stdout):
            show_rate_limits(api)

        output = stdout.getvalue()
        self.assertIn("Core API", output)
        self.assertIn("4999", output)
        self.assertIn("5000", output)
        self.assertIn("resets", output)
        # graphql has reset=0 which is falsy, so no "resets" line
        self.assertIn("GraphQL API", output)

    def test_show_rate_limits_formats_premium_tiers(self):
        from github_usage.report_account import show_rate_limits

        api = FakeAPI(
            request_responses={
                ("GET", "/rate_limit", ()): {
                    "resources": {
                        "core": {"limit": 5000, "remaining": 5000, "used": 0},
                        "core_enterprise_tier": {"limit": 10000, "remaining": 0, "used": 10000},
                    }
                }
            }
        )

        stdout = StringIO()
        with redirect_stdout(stdout):
            show_rate_limits(api)

        output = stdout.getvalue()
        # core (limit 5000) should NOT appear in premium tier
        self.assertIn("Premium API tiers:", output)
        self.assertIn("core_enterprise_tier", output)
        self.assertIn("100.0% used", output)
        # Standard tier should still print core
        self.assertIn("Core API", output)

    def test_show_rate_limits_handles_missing_or_null_remaining(self):
        """Missing keys or None default to '?'; a 0 value prints 0."""
        from github_usage.report_account import show_rate_limits

        api = FakeAPI(
            request_responses={
                ("GET", "/rate_limit", ()): {
                    "resources": {
                        # None values for both remaining and limit
                        "core": {"limit": None, "remaining": None, "used": 0, "reset": 0},
                        # 0 remaining, missing limit
                        "graphql": {"remaining": 0, "used": 0, "reset": 0},
                        # missing both keys entirely
                        "search": {"used": 0, "reset": 0},
                    }
                }
            }
        )

        stdout = StringIO()
        with redirect_stdout(stdout):
            show_rate_limits(api)

        output = stdout.getvalue()
        # core: None for both -> ?
        self.assertIn("Core API", output)
        # graphql: 0 remaining prints 0
        self.assertIn("GraphQL API", output)
        # search: missing keys default to ?
        self.assertIn("Search API", output)
        # Should not crash and the "?" literal should appear at least twice
        self.assertGreaterEqual(output.count("?"), 2)

    def test_show_rate_limits_handles_null_limit_in_premium_tier(self):
        """Premium tier with limit=None is silently skipped (None > 5000 would have raised)."""
        from github_usage.report_account import show_rate_limits

        api = FakeAPI(
            request_responses={
                ("GET", "/rate_limit", ()): {
                    "resources": {
                        "core": {"limit": 5000, "remaining": 5000, "used": 0},
                        "tier_with_null_limit": {"limit": None, "remaining": 0, "used": 100},
                    }
                }
            }
        )

        stdout = StringIO()
        with redirect_stdout(stdout):
            show_rate_limits(api)

        # Should not raise; the null-limit tier is skipped.
        output = stdout.getvalue()
        self.assertIn("Premium API tiers:", output)
        # The null-limit tier should NOT appear in premium output
        self.assertNotIn("tier_with_null_limit", output)

    def test_show_rate_limits_handles_null_used_in_premium_tier(self):
        """Premium tier with used=None does not crash; used renders as 0."""
        from github_usage.report_account import show_rate_limits

        api = FakeAPI(
            request_responses={
                ("GET", "/rate_limit", ()): {
                    "resources": {
                        "core": {"limit": 5000, "remaining": 5000, "used": 0},
                        "tier_with_null_used": {"limit": 10000, "remaining": 0, "used": None},
                    }
                }
            }
        )

        stdout = StringIO()
        with redirect_stdout(stdout):
            show_rate_limits(api)

        # Should not raise; the null-used tier is printed with used=0.
        output = stdout.getvalue()
        self.assertIn("tier_with_null_used", output)
        self.assertIn("0 / 10000", output)
        self.assertIn("0.0% used", output)

    def test_show_account_info_handles_space_limit_conversions(self):
        """Bytes→GB for numeric; omitted for 0/False/None; negative int prints -0.0 GB."""
        from github_usage.report_account import show_account_info

        # Build a single plan dict that exercises all branches.
        # We need separate test cases because /user returns one plan.
        cases = [
            (1073741824, "1.0 GB available"),  # 1 GB in bytes
            (0, "Plan:"),  # space=0 is omitted, but Plan: line still prints
            (None, "Plan:"),  # space=None is omitted
            (False, "Plan:"),  # space=False is omitted (falsy)
            ("500 MB", "500 MB available"),  # non-numeric string prints verbatim
            (-100, "-0.0 GB available"),  # negative int runs bytes→GB conversion
            ("-100", "-100 available"),  # negative string prints verbatim
        ]
        for space_value, expected_substring in cases:
            with self.subTest(space=space_value):
                api = FakeAPI(
                    request_responses={
                        ("GET", "/user", ()): {
                            "login": "octocat",
                            "plan": {"name": "p", "space": space_value},
                        }
                    }
                )
                stdout = StringIO()
                with redirect_stdout(stdout):
                    show_account_info(api)
                output = stdout.getvalue()
                self.assertIn("Plan:       p", output)
                if expected_substring == "Plan:":
                    # Space line should be absent; the "Plan:" line is always present.
                    self.assertNotIn("Space:", output)
                else:
                    self.assertIn(expected_substring, output)

    def test_show_account_info_includes_optional_plan_details(self):
        """collaborators and private_repos print only when present and truthy."""
        from github_usage.report_account import show_account_info

        api = FakeAPI(
            request_responses={
                ("GET", "/user", ()): {
                    "login": "octocat",
                    "plan": {"name": "free", "collaborators": 0, "private_repos": 5},
                }
            }
        )
        stdout = StringIO()
        with redirect_stdout(stdout):
            show_account_info(api)
        output = stdout.getvalue()
        # collaborators=0 is falsy, so should NOT print
        self.assertNotIn("Collaborators:", output)
        # private_repos=5 is truthy
        self.assertIn("Private repos: 5 allowed", output)

    def test_show_account_info_missing_plan_key(self):
        from github_usage.report_account import show_account_info

        api = FakeAPI(request_responses={("GET", "/user", ()): {"login": "octocat"}})

        stdout = StringIO()
        with redirect_stdout(stdout):
            username, _ = show_account_info(api)

        self.assertEqual(username, "octocat")
        # No plan block printed
        output = stdout.getvalue()
        self.assertNotIn("Plan:", output)

    def test_show_what_else_prints_expected_help(self):
        from github_usage.report_account import show_what_else

        api = FakeAPI()

        stdout = StringIO()
        with redirect_stdout(stdout):
            show_what_else(api, "octo-cat")

        output = stdout.getvalue()
        # 3-5 stable substrings
        self.assertIn("Other Available Data Points", output)
        self.assertIn("Products available via billing API", output)
        self.assertIn("Rate limits tracked", output)
        # Username with special character renders literally (no URL encoding)
        self.assertIn("/users/octo-cat/settings/billing/usage", output)
        self.assertIn("/users/octo-cat/settings/billing/premium_request/usage", output)
        # Should NOT be URL-encoded
        self.assertNotIn("octo%2Dcat", output)
        self.assertNotIn("octo%20cat", output)
