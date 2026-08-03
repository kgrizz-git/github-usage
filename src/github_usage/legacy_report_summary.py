"""Compact summary rows for legacy report data (TUI and other UIs)."""

from __future__ import annotations

from typing import Any

from .repo_consumers import private_list_is_redundant
from .report_forecast_data import build_report_forecast
from .report_helpers import fmt_price
from .visibility import repo_visibility, visibility_label


def _section(title: str) -> tuple[str, str]:
    """Return a section header row for two-column tables."""
    return (f"── {title} ──", "")


def _annotated_repo(item: dict[str, Any], *, key: str = "repo") -> str:
    repo = str(item.get(key, "?"))
    return f"{repo}{visibility_label(repo_visibility(item))}"


def _format_cost_block(monthly: dict[str, Any], product: str) -> str:
    block = monthly.get(product) or {}
    return fmt_price(float(block.get("net", 0.0)))


def _format_actions_minutes(data: dict[str, Any]) -> str:
    """Actions compute minutes — private-first when the visibility split exists."""
    errors = data.get("errors") or {}
    actions = data.get("actions")
    if actions is None:
        if errors.get("actions"):
            return f"n/a ({errors['actions']})"
        return "n/a"
    if "private_minutes" in actions:
        private = float(actions.get("private_minutes") or 0.0)
        public = float(actions.get("public_minutes") or 0.0)
        pct = float(actions.get("private_minutes_percent") or 0.0)
        return f"Private {private:.1f} / 2,000 min ({pct:.1f}%) · public {public:.1f} min (free)"
    minutes = float(actions.get("minutes", 0.0))
    limit = float(actions.get("minutes_limit", 2000))
    pct = float(actions.get("minutes_percent", 0.0))
    return f"{minutes:.1f} / {limit:.0f} min ({pct:.1f}%)"


def _format_actions_storage(data: dict[str, Any]) -> tuple[str, str]:
    """Billed Actions storage (GB-hrs and average MB), private-first when split."""
    errors = data.get("errors") or {}
    actions = data.get("actions")
    if actions is None:
        msg = f"n/a ({errors['actions']})" if errors.get("actions") else "n/a"
        return msg, msg
    if "private_storage_avg_mb" in actions:
        priv_mb = float(actions.get("private_storage_avg_mb") or 0.0)
        pub_mb = float(actions.get("public_storage_avg_mb") or 0.0)
        priv_gb = float(actions.get("private_storage_gb_hours") or 0.0)
        pub_gb = float(actions.get("public_storage_gb_hours") or 0.0)
        avg_line = f"Private {priv_mb:.1f} / 500 MB · public {pub_mb:.1f} MB (free)"
        gb_line = f"Private {priv_gb:.4f} GB-hrs · public {pub_gb:.4f} GB-hrs (free)"
        return avg_line, gb_line
    gb_hours = float(actions.get("storage_gb_hours", 0.0))
    avg_mb = float(actions.get("storage_avg_mb", 0.0))
    limit_mb = float(actions.get("storage_limit_mb", 500))
    pct = float(actions.get("storage_percent", 0.0))
    avg_line = f"{avg_mb:.1f} / {limit_mb:.0f} MB ({pct:.1f}%)"
    gb_line = f"{gb_hours:.4f} GB-hrs"
    return avg_line, gb_line


def _format_repo_storage_value(repo: dict[str, Any]) -> str:
    """Human-readable artifact/release/expiry line for one storage-analysis repo."""
    art_gb = float(repo.get("artifact_storage_gb", repo.get("total_storage", 0.0)) or 0.0)
    rel_gb = float(repo.get("release_storage_gb", 0.0) or 0.0)
    count = int(repo.get("artifact_count", 0) or 0)
    soon = int(repo.get("expiring_soon_count", 0) or 0)
    expired = int(repo.get("expired_count", 0) or 0)
    parts = [f"{art_gb:.2f} GB artifacts"]
    if rel_gb:
        parts.append(f"{rel_gb:.2f} GB releases (free)")
    if count:
        expiry = f"{count} artifacts"
        if soon:
            expiry += f" · {soon} expire ≤7d"
        if expired:
            expiry += f" · {expired} expired"
        parts.append(expiry)
    return " · ".join(parts)


def _artifact_release_storage_rows(
    data: dict[str, Any], *, limit: int = 10
) -> list[tuple[str, str]]:
    """Per-repo artifact and release asset totals from ``storage_analysis``."""
    storage_analysis = data.get("storage_analysis") or {}
    repos = sorted(
        storage_analysis.get("repos") or [],
        key=lambda row: float(row.get("total_storage", 0.0)),
        reverse=True,
    )
    rows: list[tuple[str, str]] = []
    total_gb = sum(float(repo.get("total_storage", 0.0)) for repo in repos)
    rows.append(("Total (artifacts + releases)", f"{total_gb:.2f} GB"))
    if not repos:
        rows.append(
            (
                "Note",
                "No artifacts or release assets found in scanned repos "
                "(see Actions storage above for billed cache/artifact usage).",
            )
        )
        return rows
    for repo in repos[:limit]:
        rows.append((_annotated_repo(repo, key="name"), _format_repo_storage_value(repo)))
    if len(repos) > limit:
        rows.append((f"… +{len(repos) - limit} more repos", ""))
    return rows


def _repo_billed_storage_rows(data: dict[str, Any], *, limit: int = 10) -> list[tuple[str, str]]:
    """Per-repo billed Actions storage from ``repo_actions``."""
    repo_actions = sorted(
        data.get("repo_actions") or [],
        key=lambda row: float(row.get("avg_mb", 0.0)),
        reverse=True,
    )
    rows: list[tuple[str, str]] = []
    with_storage = [row for row in repo_actions if float(row.get("avg_mb", 0.0)) > 0]
    if not with_storage:
        rows.append(("Note", "No per-repo billed Actions storage this period."))
        return rows
    for row in with_storage[:limit]:
        repo = _annotated_repo(row)
        avg_mb = float(row.get("avg_mb", 0.0))
        gb_hours = float(row.get("storage_gb_hours", 0.0))
        rows.append((repo, f"{avg_mb:.1f} MB avg · {gb_hours:.4f} GB-hrs"))
    if len(with_storage) > limit:
        rows.append((f"… +{len(with_storage) - limit} more repos", ""))
    return rows


def _copilot_rows(data: dict[str, Any]) -> list[tuple[str, str]]:
    """Copilot billing summary rows."""
    errors = data.get("errors") or {}
    billing = data.get("copilot_billing")
    if billing is None and errors.get("copilot_billing"):
        return [("Copilot", f"n/a ({errors['copilot_billing']})")]
    if not billing:
        copilot = data.get("copilot")
        if copilot is None and errors.get("copilot"):
            return [("Copilot", f"n/a ({errors['copilot']})")]
        if not copilot:
            return [("Copilot", "No usage")]
        return [
            ("Copilot gross", fmt_price(float(copilot.get("total_gross", 0.0)))),
            ("Copilot net", fmt_price(float(copilot.get("total_net", 0.0)))),
        ]
    rows = [
        ("Copilot gross", fmt_price(float(billing.get("total_gross", 0.0)))),
        ("Copilot net", fmt_price(float(billing.get("total_net", 0.0)))),
    ]
    by_model = (data.get("copilot") or {}).get("by_model") or {}
    for model, values in sorted(
        by_model.items(), key=lambda item: float(item[1].get("requests", 0)), reverse=True
    )[:5]:
        reqs = float(values.get("requests", 0))
        net = float(values.get("net", 0.0))
        rows.append((f"  {model}", f"{reqs:.0f} reqs · {fmt_price(net)}"))
    return rows


def _git_lfs_rows(data: dict[str, Any]) -> list[tuple[str, str]]:
    """Git LFS billing summary rows."""
    errors = data.get("errors") or {}
    billing = data.get("lfs_billing")
    if billing is None and errors.get("lfs_billing"):
        return [("Git LFS", f"n/a ({errors['lfs_billing']})")]
    if not billing or not billing.get("items"):
        git_lfs = data.get("git_lfs")
        if git_lfs is None and errors.get("git_lfs"):
            return [("Git LFS", f"n/a ({errors['git_lfs']})")]
        if not git_lfs:
            return [("Git LFS", "No usage")]
        return [("Git LFS net", fmt_price(float(git_lfs.get("total_net", 0.0))))]
    rows: list[tuple[str, str]] = [
        ("Git LFS net", fmt_price(float(billing.get("total_net", 0.0)))),
    ]
    for sku, item in billing.get("items", {}).items():
        qty = float(item.get("grossQuantity", 0.0))
        unit = item.get("unitType", "")
        net = float(item.get("netAmount", 0.0))
        rows.append((f"  {sku}", f"{qty:.4f} {unit} · {fmt_price(net)}"))
    return rows


def _forecast_rows(
    data: dict[str, Any],
    *,
    include_forecast: bool = True,
    premium_requests_limit: float | None = None,
    reference_date=None,
) -> list[tuple[str, str]]:
    """Return projected end-of-month usage rows or empty list when not computable."""
    if not include_forecast:
        return []
    forecast = build_report_forecast(
        data,
        premium_requests_limit=premium_requests_limit,
        reference_date=reference_date,
    )
    if forecast is None:
        return []

    rows: list[tuple[str, str]] = []

    minutes = forecast["minutes"]
    minutes_line = f"{minutes['projected']:.1f} / {minutes['limit']:.0f}"
    if minutes["limit"]:
        minutes_line += f" ({minutes['projected'] / minutes['limit'] * 100:.1f}%)"
    rows.append(("Projected minutes at month end", minutes_line))

    storage = forecast["storage_avg_mb"]
    storage_line = f"{storage['projected']:.1f} MB / {storage['limit']:.0f} MB"
    if storage["limit"]:
        storage_line += f" ({storage['projected'] / storage['limit'] * 100:.1f}%)"
    rows.append(("Projected storage at month end", storage_line))

    premium = forecast["premium_requests"]
    if premium_requests_limit is not None:
        premium_line = f"{premium['projected']:.1f} / {premium_requests_limit:.0f}"
        if premium_requests_limit > 0:
            premium_line += f" ({premium['projected'] / premium_requests_limit * 100:.1f}%)"
        rows.append(("Projected premium requests at month end", premium_line))
    else:
        rows.append(("Projected premium requests at month end", f"{premium['projected']:.1f}"))

    return rows


def _overview_rows(data: dict[str, Any], username: str) -> list[tuple[str, str]]:
    """Overview section rows for the detail table."""
    account = data.get("account") or {}
    plan = (account.get("plan") or {}).get("name", "n/a")
    return [
        _section("Overview"),
        ("User", str(username)),
        ("Account type", str(account.get("type", "n/a"))),
        ("Plan", str(plan)),
    ]


def _monthly_cost_rows(data: dict[str, Any]) -> list[tuple[str, str]]:
    """Monthly costs section rows for the detail table."""
    errors = data.get("errors") or {}
    monthly = data.get("monthly_costs") or {}
    rows = [_section("Monthly costs (net)")]
    if errors.get("monthly_costs"):
        rows.append(("Costs", f"n/a ({errors['monthly_costs']})"))
    else:
        rows.append(("Actions", _format_cost_block(monthly, "actions")))
        rows.append(("Copilot", _format_cost_block(monthly, "copilot")))
        rows.append(("Git LFS", _format_cost_block(monthly, "git_lfs")))
        rows.append(("Total", _format_cost_block(monthly, "total")))
    return rows


def _actions_usage_rows(
    data: dict[str, Any],
    *,
    include_forecast: bool = True,
    premium_requests_limit: float | None = None,
    reference_date=None,
) -> list[tuple[str, str]]:
    """Actions usage and forecast rows for the detail table."""
    rows = [_section("Actions usage")]
    rows.append(("Compute minutes", _format_actions_minutes(data)))
    actions = data.get("actions") or {}
    public_minutes = float(actions.get("public_minutes") or 0.0)
    if public_minutes > 0:
        rows.append(("Public Actions minutes", f"{public_minutes:,.1f} (free)"))
    avg_storage, gb_hours = _format_actions_storage(data)
    rows.append(("Storage (avg MB, billed)", avg_storage))
    rows.append(("Storage (GB-hrs, billed)", gb_hours))
    forecast_rows = _forecast_rows(
        data,
        include_forecast=include_forecast,
        premium_requests_limit=premium_requests_limit,
        reference_date=reference_date,
    )
    if forecast_rows:
        rows.append(_section("Forecast"))
        rows.extend(forecast_rows)
    return rows


def _append_consumer_minute_rows(
    rows: list[tuple[str, str]], by_minutes: list[dict[str, Any]]
) -> None:
    if not by_minutes:
        return
    rows.append(_section("Top repos by Actions minutes"))
    for item in by_minutes[:10]:
        repo = _annotated_repo(item)
        minutes = float(item.get("minutes", 0.0))
        gross = float(item.get("gross", 0.0))
        rows.append((repo, f"{minutes:.1f} min · {fmt_price(gross)}"))


def _append_consumer_cost_rows(rows: list[tuple[str, str]], by_cost: list[dict[str, Any]]) -> None:
    if not by_cost:
        return
    rows.append(_section("Top repos by Actions cost"))
    for item in by_cost[:10]:
        repo = _annotated_repo(item)
        gross = float(item.get("gross", 0.0))
        minutes = float(item.get("minutes", 0.0))
        rows.append((repo, f"{fmt_price(gross)} · {minutes:.1f} min"))


def _append_private_consumer_minute_rows(
    rows: list[tuple[str, str]],
    *,
    by_minutes: list[dict[str, Any]],
    by_minutes_private: list[dict[str, Any]],
    private_minutes_f: float | None,
) -> None:
    if not by_minutes_private or private_list_is_redundant(
        by_minutes[:10], by_minutes_private[:10]
    ):
        return
    rows.append(_section("Top private repos by Actions minutes"))
    for item in by_minutes_private[:10]:
        repo = _annotated_repo(item)
        minutes = float(item.get("minutes", 0.0))
        gross = float(item.get("gross", 0.0))
        pct = (
            minutes / private_minutes_f * 100.0
            if private_minutes_f and private_minutes_f > 0
            else 0.0
        )
        if private_minutes_f and private_minutes_f > 0:
            value = f"{minutes:.1f} min ({pct:.1f}% of private) · {fmt_price(gross)}"
        else:
            value = f"{minutes:.1f} min · {fmt_price(gross)}"
        rows.append((repo, value))


def _append_private_storage_consumer_rows(
    rows: list[tuple[str, str]],
    *,
    by_storage: list[dict[str, Any]],
    by_storage_private: list[dict[str, Any]],
) -> None:
    if not by_storage_private or private_list_is_redundant(
        by_storage[:10], by_storage_private[:10]
    ):
        return
    rows.append(_section("Top private repos by Actions storage (billed)"))
    for item in by_storage_private[:10]:
        repo = _annotated_repo(item)
        avg_mb = float(item.get("storage_avg_mb", 0.0))
        rows.append((repo, f"{avg_mb:.1f} MB avg"))


def _append_overall_storage_consumer_rows(
    rows: list[tuple[str, str]], by_storage: list[dict[str, Any]]
) -> None:
    if not by_storage:
        return
    rows.append(_section("Top repos by Actions storage (billed)"))
    for item in by_storage[:10]:
        repo = _annotated_repo(item)
        avg_mb = float(item.get("storage_avg_mb", 0.0))
        rows.append((repo, f"{avg_mb:.1f} MB avg"))


def _repo_rows(data: dict[str, Any]) -> list[tuple[str, str]]:
    """Repository-related rows for the detail table."""
    rows: list[tuple[str, str]] = []
    consumers = data.get("repo_consumers") or {}
    by_minutes = consumers.get("by_minutes") or []
    by_cost = consumers.get("by_cost") or []
    by_storage = consumers.get("by_storage") or []
    by_minutes_private = consumers.get("by_minutes_private") or []
    by_storage_private = consumers.get("by_storage_private") or []
    private_minutes = (data.get("actions") or {}).get("private_minutes")
    private_minutes_f = float(private_minutes) if private_minutes is not None else None

    _append_consumer_minute_rows(rows, by_minutes)
    _append_consumer_cost_rows(rows, by_cost)
    _append_private_consumer_minute_rows(
        rows,
        by_minutes=by_minutes,
        by_minutes_private=by_minutes_private,
        private_minutes_f=private_minutes_f,
    )
    _append_private_storage_consumer_rows(
        rows,
        by_storage=by_storage,
        by_storage_private=by_storage_private,
    )
    _append_overall_storage_consumer_rows(rows, by_storage)

    billed_storage = _repo_billed_storage_rows(data)
    if billed_storage:
        rows.append(_section("Per-repo Actions storage (billed)"))
        rows.extend(billed_storage)

    rows.append(_section("Artifact & release storage (API scan)"))
    rows.extend(_artifact_release_storage_rows(data))

    artifact_storage = data.get("artifact_storage") or {}
    top_artifacts = artifact_storage.get("top_repos") or []
    if top_artifacts:
        rows.append(_section("Largest artifact storage"))
        for item in top_artifacts[:5]:
            repo = _annotated_repo(item)
            gb = float(item.get("artifact_bytes", 0)) / (1024**3)
            rows.append((repo, f"{gb:.2f} GB"))

    return rows


def _tail_rows(data: dict[str, Any]) -> list[tuple[str, str]]:
    """Copilot, LFS, insights, warnings, and section-error rows."""
    rows: list[tuple[str, str]] = []
    errors = data.get("errors") or {}

    copilot_rows = _copilot_rows(data)
    if copilot_rows:
        rows.append(_section("Copilot"))
        rows.extend(copilot_rows)

    lfs_rows = _git_lfs_rows(data)
    if lfs_rows:
        rows.append(_section("Git LFS"))
        rows.extend(lfs_rows)

    insights = data.get("insights") or []
    if insights:
        rows.append(_section("Insights"))
        for index, insight in enumerate(insights, start=1):
            rows.append((f"{index}.", str(insight)))

    warnings = data.get("warnings") or []
    if warnings:
        rows.append(_section("Warnings"))
        for index, warning in enumerate(warnings, start=1):
            rows.append((f"{index}.", str(warning)))

    section_errors = [
        (key, message)
        for key, message in sorted(errors.items())
        if key
        not in {
            "actions",
            "copilot",
            "git_lfs",
            "monthly_costs",
            "copilot_billing",
            "lfs_billing",
            "copilot_premium",
        }
    ]
    if section_errors:
        rows.append(_section("Section errors"))
        for key, message in section_errors:
            rows.append((key, message))

    return rows


def legacy_report_detail_rows(
    data: dict[str, Any],
    username: str,
    *,
    include_forecast: bool = True,
    premium_requests_limit: float | None = None,
    reference_date=None,
) -> list[tuple[str, str]]:
    """Return full legacy report rows for TUI tables (section headers + detail)."""
    return [
        *_overview_rows(data, username),
        *_monthly_cost_rows(data),
        *_actions_usage_rows(
            data,
            include_forecast=include_forecast,
            premium_requests_limit=premium_requests_limit,
            reference_date=reference_date,
        ),
        *_repo_rows(data),
        *_tail_rows(data),
    ]


def legacy_report_summary_rows(data: dict[str, Any], username: str) -> list[tuple[str, str]]:
    """Return primary summary rows (overview + key usage only)."""
    avg_storage, _gb_hours = _format_actions_storage(data)
    storage_analysis = data.get("storage_analysis") or {}
    artifact_gb = sum(
        float(repo.get("total_storage", 0.0)) for repo in storage_analysis.get("repos") or []
    )
    monthly = data.get("monthly_costs") or {}
    return [
        ("User", str(username)),
        ("Total spend (net)", _format_cost_block(monthly, "total")),
        ("Actions minutes", _format_actions_minutes(data)),
        ("Actions storage (avg MB)", avg_storage),
        ("Artifacts/releases (scan)", f"{artifact_gb:.2f} GB"),
    ]


def legacy_report_consumer_rows(data: dict[str, Any], *, limit: int = 10) -> list[tuple[str, str]]:
    """Return top repo consumer rows from ``repo_consumers.by_minutes``."""
    consumers = (data.get("repo_consumers") or {}).get("by_minutes") or []
    rows: list[tuple[str, str]] = []
    for item in consumers[:limit]:
        repo = _annotated_repo(item)
        minutes = float(item.get("minutes", 0.0))
        rows.append((f"Repo: {repo}", f"{minutes:.1f} min"))
    return rows
