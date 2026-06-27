"""Billing and usage data collectors."""

from __future__ import annotations

from datetime import date, timedelta

from .report_helpers import sanitize_item_amounts


class BillingFetchError(RuntimeError):
    """Raised when a per-repo billing API call fails."""


def _safe_amount(item: dict, key: str) -> float:
    """Read a numeric amount from an item dict, treating None as 0.0."""
    val = item.get(key)
    return float(val) if val is not None else 0.0


def get_billing_summary(api, username, product):
    """Get usage summary for a product. Returns parsed items dict keyed by sku."""
    try:
        billing = api.request(
            "GET", f"/users/{username}/settings/billing/usage/summary", {"product": product}
        )
    except RuntimeError:
        return None
    if not billing:
        return None
    if not isinstance(billing, dict):
        return None
    items = billing.get("usageItems", [])
    summary = {"raw": billing, "items": {}, "total_gross": 0, "total_discount": 0, "total_net": 0}
    for item in items:
        sku = item.get("sku", item.get("product", "unknown"))
        sanitized = sanitize_item_amounts(item)
        summary["items"][sku] = sanitized
        summary["total_gross"] += _safe_amount(sanitized, "grossAmount")
        summary["total_discount"] += _safe_amount(sanitized, "discountAmount")
        summary["total_net"] += _safe_amount(sanitized, "netAmount")
    return summary


def get_premium_request_usage(api, username, product="copilot", model=None):
    """Get premium request usage breakdown by model."""
    params = {"product": product}
    if model:
        params["model"] = model
    try:
        data = api.request(
            "GET",
            f"/users/{username}/settings/billing/premium_request/usage",
            params if params else None,
        )
    except RuntimeError:
        return None
    if not data:
        return None
    if not isinstance(data, dict):
        return None
    items = data.get("usageItems", [])
    by_model = {}
    for item in items:
        m = item.get("model", "Unknown")
        if m not in by_model:
            by_model[m] = {
                "items": [],
                "total_requests": 0,
                "total_gross": 0,
                "total_discount": 0,
                "total_net": 0,
            }
        sanitized = sanitize_item_amounts(item)
        by_model[m]["items"].append(sanitized)
        by_model[m]["total_requests"] += _safe_amount(sanitized, "grossQuantity")
        by_model[m]["total_gross"] += _safe_amount(sanitized, "grossAmount")
        by_model[m]["total_discount"] += _safe_amount(sanitized, "discountAmount")
        by_model[m]["total_net"] += _safe_amount(sanitized, "netAmount")
    return by_model


def get_full_billing(api, username):
    """Get full billing usage report (all products, all time this year)."""
    try:
        data = api.request("GET", f"/users/{username}/settings/billing/usage")
    except RuntimeError:
        return None
    if not data:
        return None
    if not isinstance(data, dict):
        return None
    return data.get("usageItems", [])


def get_user_actions_billing(api, username):
    """Get user-level Actions billing. Returns (total_minutes, storage_gb_hours, sku_breakdown)."""
    summary = get_billing_summary(api, username, "Actions")
    if not summary:
        return None, None, {}
    total_minutes = 0.0
    total_storage_gb_hours = 0.0
    sku_breakdown = {}
    for sku, item in summary["items"].items():
        unit = item.get("unitType", "")
        qty = _safe_amount(item, "grossQuantity")
        if unit == "minutes":
            total_minutes += qty
        elif unit == "gigabyte-hours":
            total_storage_gb_hours += qty
        sku_breakdown[sku] = item
    return total_minutes, total_storage_gb_hours, sku_breakdown


def get_actions_per_repo(api, owner, repo):
    """Get per-repo Actions billing."""
    try:
        billing = api.request(
            "GET",
            f"/users/{owner}/settings/billing/usage/summary",
            {"product": "Actions", "repository": f"{owner}/{repo}"},
        )
    except RuntimeError as e:
        raise BillingFetchError(f"{owner}/{repo}: {e}") from e
    if not billing:
        return 0.0, 0.0, {}
    if not isinstance(billing, dict):
        return 0.0, 0.0, {}
    total_minutes = 0.0
    total_storage_gb_hours = 0.0
    sku_breakdown = {}
    for item in billing.get("usageItems", []):
        sku = item.get("sku", "unknown")
        sanitized = sanitize_item_amounts(item)
        unit = sanitized.get("unitType", "")
        qty = _safe_amount(sanitized, "grossQuantity")
        if unit == "minutes":
            total_minutes += qty
        elif unit == "gigabyte-hours":
            total_storage_gb_hours += qty
        sku_breakdown[sku] = sanitized
    return total_minutes, total_storage_gb_hours, sku_breakdown


def get_actions_from_runs(api, owner, repo):
    """Fallback: calculate minutes from workflow runs."""
    first_day = date.today().replace(day=1)
    last_day = (first_day.replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(days=1)
    created_range = f"{first_day.isoformat()}..{last_day.isoformat()}"
    runs = api.get_all_pages(
        f"/repos/{owner}/{repo}/actions/runs",
        {"created": created_range, "per_page": 100},
    )
    if not runs:
        runs = []
    total_minutes = 0.0
    workflow_minutes = {}
    os_millis = {"UBUNTU": 0, "WINDOWS": 0, "MACOS": 0}
    for run in runs:
        billable = run.get("billable") or {}
        run_minutes = 0.0
        for os_name in ["UBUNTU", "WINDOWS", "MACOS"]:
            millis = (billable.get(os_name) or {}).get("millis", 0)
            os_millis[os_name] += millis
            run_minutes += millis / 60000
        total_minutes += run_minutes
        wf_name = run.get("workflow_name", "Unknown")
        workflow_minutes[wf_name] = workflow_minutes.get(wf_name, 0) + run_minutes
    return round(total_minutes, 1), os_millis, workflow_minutes
