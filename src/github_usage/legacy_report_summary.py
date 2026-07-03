"""Compact summary rows for legacy report data (TUI and other UIs)."""

from __future__ import annotations

from typing import Any

from .report_helpers import fmt_price


def _section(title: str) -> tuple[str, str]:
    """Return a section header row for two-column tables."""
    return (f"── {title} ──", "")


def _format_cost_block(monthly: dict[str, Any], product: str) -> str:
    block = monthly.get(product) or {}
    return fmt_price(float(block.get("net", 0.0)))


def _format_actions_minutes(data: dict[str, Any]) -> str:
    """Actions compute minutes from ``actions.minutes``."""
    errors = data.get("errors") or {}
    actions = data.get("actions")
    if actions is None:
        if errors.get("actions"):
            return f"n/a ({errors['actions']})"
        return "n/a"
    minutes = float(actions.get("minutes", 0.0))
    limit = float(actions.get("minutes_limit", 2000))
    pct = float(actions.get("minutes_percent", 0.0))
    return f"{minutes:.1f} / {limit:.0f} min ({pct:.1f}%)"


def _format_actions_storage(data: dict[str, Any]) -> tuple[str, str]:
    """Billed Actions storage (GB-hrs and average MB)."""
    errors = data.get("errors") or {}
    actions = data.get("actions")
    if actions is None:
        msg = f"n/a ({errors['actions']})" if errors.get("actions") else "n/a"
        return msg, msg
    gb_hours = float(actions.get("storage_gb_hours", 0.0))
    avg_mb = float(actions.get("storage_avg_mb", 0.0))
    limit_mb = float(actions.get("storage_limit_mb", 500))
    pct = float(actions.get("storage_percent", 0.0))
    avg_line = f"{avg_mb:.1f} / {limit_mb:.0f} MB ({pct:.1f}%)"
    gb_line = f"{gb_hours:.4f} GB-hrs"
    return avg_line, gb_line


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
        name = repo.get("name", "?")
        gb = float(repo.get("total_storage", 0.0))
        value = f"{gb:.2f} GB" if gb > 0 else "0"
        rows.append((name, value))
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
        repo = row.get("repo", "?")
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


def legacy_report_detail_rows(data: dict[str, Any], username: str) -> list[tuple[str, str]]:
    """Return full legacy report rows for TUI tables (section headers + detail)."""
    rows: list[tuple[str, str]] = []
    errors = data.get("errors") or {}
    monthly = data.get("monthly_costs") or {}
    account = data.get("account") or {}
    plan = (account.get("plan") or {}).get("name", "n/a")

    rows.append(_section("Overview"))
    rows.append(("User", str(username)))
    rows.append(("Account type", str(account.get("type", "n/a"))))
    rows.append(("Plan", str(plan)))

    rows.append(_section("Monthly costs (net)"))
    if errors.get("monthly_costs"):
        rows.append(("Costs", f"n/a ({errors['monthly_costs']})"))
    else:
        rows.append(("Actions", _format_cost_block(monthly, "actions")))
        rows.append(("Copilot", _format_cost_block(monthly, "copilot")))
        rows.append(("Git LFS", _format_cost_block(monthly, "git_lfs")))
        rows.append(("Total", _format_cost_block(monthly, "total")))

    rows.append(_section("Actions usage"))
    rows.append(("Compute minutes", _format_actions_minutes(data)))
    avg_storage, gb_hours = _format_actions_storage(data)
    rows.append(("Storage (avg MB, billed)", avg_storage))
    rows.append(("Storage (GB-hrs, billed)", gb_hours))

    consumers = data.get("repo_consumers") or {}
    by_minutes = consumers.get("by_minutes") or []
    by_cost = consumers.get("by_cost") or []

    if by_minutes:
        rows.append(_section("Top repos by Actions minutes"))
        for item in by_minutes[:10]:
            repo = item.get("repo", "?")
            minutes = float(item.get("minutes", 0.0))
            gross = float(item.get("gross", 0.0))
            rows.append((repo, f"{minutes:.1f} min · {fmt_price(gross)}"))

    if by_cost:
        rows.append(_section("Top repos by Actions cost"))
        for item in by_cost[:10]:
            repo = item.get("repo", "?")
            gross = float(item.get("gross", 0.0))
            minutes = float(item.get("minutes", 0.0))
            rows.append((repo, f"{fmt_price(gross)} · {minutes:.1f} min"))

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
            repo = item.get("repo", "?")
            gb = float(item.get("artifact_bytes", 0)) / (1024**3)
            rows.append((repo, f"{gb:.2f} GB"))

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
        repo = item.get("repo", "?")
        minutes = float(item.get("minutes", 0.0))
        rows.append((f"Repo: {repo}", f"{minutes:.1f} min"))
    return rows
