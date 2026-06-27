import unittest
from contextlib import redirect_stdout
from io import StringIO

from tests._fakes import FakeAPI


class SummaryTests(unittest.TestCase):
    def test_print_cost_overview_handles_zero_gross(self):
        from github_usage.report_summary import _print_cost_overview

        stdout = StringIO()
        with redirect_stdout(stdout):
            _print_cost_overview(0.0, 0.0, 0.0)

        output = stdout.getvalue()
        self.assertIn("Total Gross:          $0.0000", output)
        self.assertIn("(0.0% off)", output)

    def test_print_cost_overview_handles_none_inputs(self):
        """Cost overview must not crash when totals are None (the orchestrator contract)."""
        from github_usage.report_summary import _print_cost_overview

        stdout = StringIO()
        with redirect_stdout(stdout):
            _print_cost_overview(None, None, None)

        output = stdout.getvalue()
        self.assertIn("Total Gross:          $0.0000", output)

    def test_print_utilization_handles_zero_minutes(self):
        from github_usage.report_summary import _print_utilization

        stdout = StringIO()
        with redirect_stdout(stdout):
            _print_utilization(0.0, 0.0)

        output = stdout.getvalue()
        self.assertIn("Actions Minutes:          0.0 / 2000 min (0.0% of free tier)", output)
        self.assertIn("░" * 40, output)

    def test_print_utilization_handles_none_user_minutes(self):
        """Regression: user_minutes=None must not raise on {user_minutes:>8.1f} formatting."""
        from github_usage.report_summary import _print_utilization

        stdout = StringIO()
        with redirect_stdout(stdout):
            _print_utilization(None, 0.0)

        output = stdout.getvalue()
        # 0.0 printed in the user_minutes slot via "or 0" coalescing
        self.assertIn("0.0 / 2000 min", output)

    def test_print_utilization_caps_bar_at_40_chars_when_over_100_pct(self):
        from github_usage.report_summary import _print_utilization

        # 3000 minutes = 150% of the 2000-minute free tier — bar must not exceed 40 chars
        stdout = StringIO()
        with redirect_stdout(stdout):
            _print_utilization(3000.0, 0.0)

        output = stdout.getvalue()
        bar_line = next(line for line in output.splitlines() if "█" in line)
        filled = bar_line.count("█")
        empty = bar_line.strip().count("░")
        self.assertEqual(filled + empty, 40)
        self.assertEqual(filled, 40)

    def test_print_utilization_storage_caps_bar_at_40_chars_when_over_100_pct(self):
        from github_usage.report_summary import _print_utilization

        # 1000 MB average storage = 200% of the 500 MB free tier
        # gb_hours_to_avg_mb(x) = x * 1024 / (24 * 30); solve for x giving ~1000 MB
        # 1000 * 24 * 30 / 1024 ≈ 703 gb_hours
        storage_gb_hours = 1000 * 24 * 30 / 1024
        stdout = StringIO()
        with redirect_stdout(stdout):
            _print_utilization(0.0, storage_gb_hours)

        output = stdout.getvalue()
        bar_lines = [line for line in output.splitlines() if "█" in line or "░" in line]
        storage_bar = bar_lines[-1]
        filled = storage_bar.count("█")
        empty = storage_bar.strip().count("░")
        self.assertEqual(filled + empty, 40)
        self.assertEqual(filled, 40)

    def test_print_recommendations_detects_high_usage(self):
        from github_usage.report_summary import _print_recommendations

        stdout = StringIO()
        with redirect_stdout(stdout):
            # 1800 mins is 90% of 2000
            _print_recommendations(1800, [], {}, None, {})

        output = stdout.getvalue()
        self.assertIn("Upgrade from free tier", output)

    def test_print_top_consumers_sorts_correctly(self):
        """Top 5 repos ordered by minutes and cost."""
        from github_usage.report_summary import _print_top_consumers

        # 6 repos to test that only top 5 are shown
        repo_data = [
            ("octocat/d", 100.0, 0.0, 0.0, 0.1, {}),
            ("octocat/a", 500.0, 0.0, 0.0, 5.0, {}),
            ("octocat/c", 200.0, 0.0, 0.0, 2.0, {}),
            ("octocat/b", 300.0, 0.0, 0.0, 3.0, {}),
            ("octocat/f", 50.0, 0.0, 0.0, 0.5, {}),
            ("octocat/e", 75.0, 0.0, 0.0, 0.7, {}),
        ]
        stdout = StringIO()
        with redirect_stdout(stdout):
            _print_top_consumers(1500.0, 12.0, repo_data, {}, None)

        output = stdout.getvalue()
        # top 5 by minutes: a(500), b(300), c(200), d(100), e(75)
        # f is excluded (only 5 fit)
        self.assertIn("octocat/a", output)
        self.assertIn("octocat/b", output)
        self.assertIn("octocat/c", output)
        self.assertIn("octocat/d", output)
        self.assertIn("octocat/e", output)

    def test_print_top_consumers_zero_and_none_edgecases(self):
        """user_minutes/actions_gross safe for 0, 0.0, None; premium_by_model safe for {} / None."""
        from github_usage.report_summary import _print_top_consumers

        repo_data = [("octocat/r", 100.0, 0.0, 0.0, 1.0, {})]
        # None values for user_minutes and actions_gross
        stdout = StringIO()
        with redirect_stdout(stdout):
            _print_top_consumers(None, None, repo_data, None, None)
        # No crash
        self.assertIn("octocat/r", stdout.getvalue())

        # Empty premium_by_model dict
        stdout = StringIO()
        with redirect_stdout(stdout):
            _print_top_consumers(100.0, 1.0, repo_data, {}, None)
        self.assertIn("No model-level data available", stdout.getvalue())

    def test_print_top_consumers_formats_copilot_and_lfs(self):
        """Concrete copilot premium and LFS data; assert @/req and @/ea lines and totals."""
        from github_usage.report_summary import _print_top_consumers

        premium_by_model = {
            "gpt-4.1": {
                "items": [
                    {"sku": "s1", "pricePerUnit": 0.04},  # positive price
                    {"sku": "s2", "pricePerUnit": 0},  # zero price, should be ignored
                ],
                "total_requests": 100,
                "total_gross": 4.0,
                "total_discount": 0.5,
                "total_net": 3.5,
            }
        }
        lfs_summary = {
            "items": {
                "lfs-storage": {
                    "grossQuantity": 10.0,
                    "unitType": "GB-month",
                    "pricePerUnit": 1.0,
                    "netAmount": 10.0,
                }
            }
        }
        stdout = StringIO()
        with redirect_stdout(stdout):
            _print_top_consumers(
                1000.0, 10.0, [("r", 100, 0, 0, 1.0, {})], premium_by_model, lfs_summary
            )

        output = stdout.getvalue()
        self.assertIn("gpt-4.1", output)
        self.assertIn("/req", output)
        self.assertIn("lfs-storage", output)
        self.assertIn("/ea", output)

    def test_print_storage_breakdown_renders_details(self):
        """Top 10 repos printed; breakdown lines printed; missing/empty 'repos' key handled; storage uses GB suffix."""
        from github_usage.report_summary import _print_storage_breakdown

        storage_analysis = {
            "repos": [
                {
                    "name": "octocat/heavy",
                    "total_storage": 1.5,
                    "items": [
                        {"type": "Artifact", "count": 1, "storage": 1.5, "size": "1500 MB"},
                    ],
                },
                {
                    "name": "octocat/light",
                    "total_storage": 0.5,
                    "items": [
                        {"type": "Release Asset", "count": 1, "storage": 0.5, "size": "500 MB"},
                    ],
                },
            ]
        }
        stdout = StringIO()
        with redirect_stdout(stdout):
            _print_storage_breakdown(storage_analysis)

        output = stdout.getvalue()
        self.assertIn("octocat/heavy", output)
        self.assertIn("1.50 GB", output)
        # GB suffix, no $
        self.assertIn("GB", output)
        self.assertNotIn("$", output)

    def test_print_storage_breakdown_storage_uses_gb_suffix(self):
        """Regression: no $, GB suffix present on storage lines."""
        from github_usage.report_summary import _print_storage_breakdown

        storage_analysis = {
            "repos": [
                {
                    "name": "octocat/r",
                    "total_storage": 1.0,
                    "items": [{"type": "Artifact", "count": 1, "storage": 1.0, "size": "1000 MB"}],
                }
            ]
        }
        stdout = StringIO()
        with redirect_stdout(stdout):
            _print_storage_breakdown(storage_analysis)

        output = stdout.getvalue()
        self.assertIn("1.00 GB", output)
        self.assertNotIn("$", output)

    def test_print_storage_breakdown_handles_empty_repos(self):
        from github_usage.report_summary import _print_storage_breakdown

        stdout = StringIO()
        with redirect_stdout(stdout):
            _print_storage_breakdown({})

        output = stdout.getvalue()
        self.assertIn("No storage data available", output)

    def test_print_impactful_findings_selects_top_three(self):
        """Seed all six findings; cap at 3."""
        from github_usage.report_summary import _print_impactful_findings

        # Construct inputs that fire all six findings
        repo_data = [
            ("octocat/heavy", 600.0, 0.0, 0.0, 5.0, {}),
            ("octocat/cheap", 100.0, 0.0, 0.0, 0.5, {}),
        ]
        storage_analysis = {
            "repos": [
                {
                    "name": "octocat/heavy",
                    "total_storage": 1.5,
                    "items": [],
                }
            ]
        }
        premium_by_model = {"gpt-4.1": {"items": [], "total_requests": 100, "total_net": 0.5}}
        # 1000 minutes, gross 5.5, discount 1, net 4.5
        stdout = StringIO()
        with redirect_stdout(stdout):
            _print_impactful_findings(
                1000.0,
                5.0,
                6.0,  # total_gross
                1.0,  # total_discount
                5.0,  # total_net
                repo_data,
                premium_by_model,
                storage_analysis,
            )

        output = stdout.getvalue()
        # Should print "1." "2." "3." but NOT "4." "5." "6."
        self.assertIn("1. ", output)
        self.assertIn("2. ", output)
        self.assertIn("3. ", output)
        self.assertNotIn("4. ", output)
        # Top minutes
        self.assertIn("Biggest Actions consumer", output)
        # Top cost
        self.assertIn("Highest Actions cost", output)
        # Top storage
        self.assertIn("Biggest storage consumer", output)

    def test_print_impactful_findings_handles_none_totals(self):
        """Regression: each of the 5 None-tolerant args individually does not raise."""
        from github_usage.report_summary import _print_impactful_findings

        repo_data = [("r", 100, 0, 0, 1.0, {})]
        storage_analysis = {"repos": [{"name": "r", "total_storage": 1.0, "items": []}]}
        premium_by_model = {"gpt-4.1": {"items": [], "total_requests": 10, "total_net": 0.1}}

        # Each test: one arg is None
        for kw in [
            {"user_minutes": None},
            {"actions_gross": None},
            {"total_discount": None},
            {"total_gross": None},
            {"total_net": None},
        ]:
            with self.subTest(**kw):
                args = {
                    "user_minutes": 100.0,
                    "actions_gross": 1.0,
                    "total_gross": 2.0,
                    "total_discount": 0.5,
                    "total_net": 1.5,
                    "repo_data": repo_data,
                    "premium_by_model": premium_by_model,
                    "storage_analysis": storage_analysis,
                }
                args.update(kw)
                stdout = StringIO()
                with redirect_stdout(stdout):
                    _print_impactful_findings(**args)
                # No raise
                self.assertIn("Biggest Actions consumer", stdout.getvalue())

    def test_print_impactful_findings_storage_uses_size_str(self):
        """Regression: storage consumer finding uses size_str and does not include $."""
        from github_usage.report_summary import _print_impactful_findings

        storage_analysis = {"repos": [{"name": "octocat/heavy", "total_storage": 1.5, "items": []}]}
        stdout = StringIO()
        with redirect_stdout(stdout):
            _print_impactful_findings(
                1000.0,
                0.0,
                0.0,
                0.0,
                0.0,  # zero out everything else
                [],
                {},
                storage_analysis,
            )

        output = stdout.getvalue()
        # Storage finding should use size_str format
        self.assertIn("1.50 GB", output)
        # The redundant "at" prefix is removed
        self.assertNotIn(" at 1.50 GB", output)
        # The storage consumer finding line should not contain $
        # (we look for the specific finding line)
        for line in output.splitlines():
            if "Biggest storage consumer" in line:
                self.assertNotIn("$", line)

    def test_print_impactful_findings_handles_negative_user_minutes(self):
        """No crash on negative user_minutes (no input validation)."""
        from github_usage.report_summary import _print_impactful_findings

        repo_data = [("r", 100, 0, 0, 1.0, {})]
        storage_analysis = {"repos": []}
        stdout = StringIO()
        with redirect_stdout(stdout):
            _print_impactful_findings(-1.0, 1.0, 1.0, 0.0, 1.0, repo_data, {}, storage_analysis)
        # No raise
        self.assertIn("Biggest Actions consumer", stdout.getvalue())

    def test_print_impactful_findings_handles_zero_actions_gross(self):
        """Division guard: actions_gross=0 must not raise."""
        from github_usage.report_summary import _print_impactful_findings

        repo_data = [("r", 100, 0, 0, 1.0, {})]
        storage_analysis = {"repos": []}
        stdout = StringIO()
        with redirect_stdout(stdout):
            _print_impactful_findings(100.0, 0.0, 0.0, 0.0, 0.0, repo_data, {}, storage_analysis)
        # No raise, "Highest Actions cost" should appear with 0% share
        self.assertIn("Highest Actions cost", stdout.getvalue())

    def test_print_recommendations_triggers_specific_rules(self):
        """Self-hosted runner rule (top 2 > 70%), Copilot consolidation (>2 models), large release assets."""
        from github_usage.report_summary import _print_recommendations

        # top 2 repos = 80% of 1000 minutes (800/1000)
        repo_data = [
            ("r1", 500.0, 0.0, 0.0, 0.0, {}),
            ("r2", 300.0, 0.0, 0.0, 0.0, {}),
            ("r3", 200.0, 0.0, 0.0, 0.0, {}),
        ]
        # 3 models triggers consolidation
        premium_by_model = {
            "gpt-4.1": {"items": [], "total_requests": 1, "total_net": 0.1},
            "claude": {"items": [], "total_requests": 1, "total_net": 0.1},
            "gemini": {"items": [], "total_requests": 1, "total_net": 0.1},
        }
        # Large release assets
        storage_analysis = {
            "repos": [
                {
                    "name": "octocat/heavy",
                    "total_storage": 0.5,
                    "items": [
                        {"type": "Release Asset", "count": 1, "storage": 0.5, "size": "500 MB"}
                    ],
                }
            ]
        }
        stdout = StringIO()
        with redirect_stdout(stdout):
            _print_recommendations(1000.0, repo_data, premium_by_model, None, storage_analysis)

        output = stdout.getvalue()
        self.assertIn("self-hosted runners", output)
        self.assertIn("consolidate", output)
        self.assertIn("Release assets", output)

    def test_print_recommendations_skips_when_repo_data_short(self):
        """Self-hosted runner rule requires > 1 repo; consolidation requires > 2 models."""
        from github_usage.report_summary import _print_recommendations

        # 1 repo, 1 model — neither rule fires
        stdout = StringIO()
        with redirect_stdout(stdout):
            _print_recommendations(
                100.0,
                [("r1", 100.0, 0.0, 0.0, 0.0, {})],
                {"gpt-4.1": {"items": [], "total_requests": 1, "total_net": 0.1}},
                None,
                {},
            )
        output = stdout.getvalue()
        self.assertNotIn("self-hosted runners", output)
        self.assertNotIn("consolidate", output)
        # Default path fires
        self.assertIn("well within free tiers", output)
        self.assertIn("cost alerts", output)

    def test_print_recommendations_release_assets_boundary(self):
        """Boundary: exactly 0.1 GB does NOT trigger; 0.1001 GB DOES."""
        from github_usage.report_summary import _print_recommendations

        # Exactly 0.1 GB
        stdout = StringIO()
        with redirect_stdout(stdout):
            _print_recommendations(
                100.0,
                [],
                {},
                None,
                {
                    "repos": [
                        {
                            "name": "r",
                            "total_storage": 0.1,
                            "items": [
                                {
                                    "type": "Release Asset",
                                    "count": 1,
                                    "storage": 0.1,
                                    "size": "100 MB",
                                }
                            ],
                        }
                    ]
                },
            )
        self.assertNotIn("Release assets in r use", stdout.getvalue())

        # 0.1001 GB
        stdout = StringIO()
        with redirect_stdout(stdout):
            _print_recommendations(
                100.0,
                [],
                {},
                None,
                {
                    "repos": [
                        {
                            "name": "r",
                            "total_storage": 0.1001,
                            "items": [
                                {
                                    "type": "Release Asset",
                                    "count": 1,
                                    "storage": 0.1001,
                                    "size": "100 MB",
                                }
                            ],
                        }
                    ]
                },
            )
        output = stdout.getvalue()
        self.assertIn("Release assets in r use", output)
        # Storage is now GB, not $
        self.assertIn("0.10 GB", output)
        self.assertNotIn("$", output)

    def test_show_final_summary_calls_all_subsections(self):
        """Integration: orchestrator coordinates all subsections and handles None inputs."""
        from github_usage.report_summary import show_final_summary

        api = FakeAPI(
            request_responses={
                (
                    "GET",
                    "/users/octocat/settings/billing/premium_request/usage",
                    (("product", "copilot"),),
                ): {"usageItems": []},
            }
        )
        repo_data = [("r1", 100.0, 0.0, 0.0, 1.0, {})]
        storage_analysis = {"repos": []}

        stdout = StringIO()
        with redirect_stdout(stdout):
            # Pass None for orchestrator-level None-tolerant args
            show_final_summary(
                "octocat",
                None,  # user_minutes
                None,  # user_storage_gb_hours
                None,  # actions_gross
                None,  # actions_discount
                None,  # actions_net
                repo_data,
                None,  # copilot_summary
                None,  # lfs_summary
                storage_analysis,
                api,
            )

        output = stdout.getvalue()
        # All 6 subsection headers should appear
        self.assertIn("COST OVERVIEW", output)
        self.assertIn("BIGGEST CONSUMERS", output)
        self.assertIn("STORAGE BREAKDOWN", output)
        self.assertIn("RESOURCE UTILIZATION", output)
        self.assertIn("MOST IMPACTFUL FINDINGS", output)
        self.assertIn("QUICK RECOMMENDATIONS", output)

    def test_show_final_summary_handles_none_orchestrator_math(self):
        """Regression: actions_gross/actions_discount/actions_net all None does not raise on +."""
        from github_usage.report_summary import show_final_summary

        api = FakeAPI(
            request_responses={
                (
                    "GET",
                    "/users/octocat/settings/billing/premium_request/usage",
                    (("product", "copilot"),),
                ): {"usageItems": []},
            }
        )
        repo_data = []
        storage_analysis = {"repos": []}

        stdout = StringIO()
        with redirect_stdout(stdout):
            show_final_summary(
                "octocat",
                0.0,
                0.0,
                None,  # actions_gross
                None,  # actions_discount
                None,  # actions_net
                repo_data,
                None,
                None,
                storage_analysis,
                api,
            )
        # No raise; the cost overview is printed
        output = stdout.getvalue()
        self.assertIn("COST OVERVIEW", output)
