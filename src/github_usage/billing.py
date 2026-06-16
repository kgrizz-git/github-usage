"""Billing and usage data collectors."""

from __future__ import annotations

from datetime import date, timedelta


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
    items = billing.get("usageItems", [])
    summary = {"raw": billing, "items": {}, "total_gross": 0, "total_discount": 0, "total_net": 0}
    for item in items:
        sku = item.get("sku", item.get("product", "unknown"))
        summary["items"][sku] = item
        summary["total_gross"] += item.get("grossAmount", 0)
        summary["total_discount"] += item.get("discountAmount", 0)
        summary["total_net"] += item.get("netAmount", 0)
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
        by_model[m]["items"].append(item)
        by_model[m]["total_requests"] += item.get("grossQuantity", 0)
        by_model[m]["total_gross"] += item.get("grossAmount", 0)
        by_model[m]["total_discount"] += item.get("discountAmount", 0)
        by_model[m]["total_net"] += item.get("netAmount", 0)
    return by_model


def get_full_billing(api, username):
    """Get full billing usage report (all products, all time this year)."""
    try:
        data = api.request("GET", f"/users/{username}/settings/billing/usage")
    except RuntimeError:
        return None
    if not data:
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
        qty = item.get("grossQuantity", 0)
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
    except RuntimeError:
        return 0.0, 0.0, {}
    if not billing:
        return 0.0, 0.0, {}
    total_minutes = 0.0
    total_storage_gb_hours = 0.0
    sku_breakdown = {}
    for item in billing.get("usageItems", []):
        sku = item.get("sku", "unknown")
        unit = item.get("unitType", "")
        qty = item.get("grossQuantity", 0)
        if unit == "minutes":
            total_minutes += qty
        elif unit == "gigabyte-hours":
            total_storage_gb_hours += qty
        sku_breakdown[sku] = item
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
    total_minutes = 0.0
    workflow_minutes = {}
    os_minutes = {"UBUNTU": 0, "WINDOWS": 0, "MACOS": 0}
    for run in runs:
        billable = run.get("billable") or {}
        for os_name in ["UBUNTU", "WINDOWS", "MACOS"]:
            millis = billable.get(os_name, {}).get("millis", 0)
            os_minutes[os_name] += millis
            total_minutes += millis / 60000
        wf_name = run.get("workflow_name", "Unknown")
        workflow_minutes[wf_name] = workflow_minutes.get(wf_name, 0) + total_minutes
    return round(total_minutes, 1), os_minutes, workflow_minutes
