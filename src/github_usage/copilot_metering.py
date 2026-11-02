"""Copilot usage metering helpers (AI credits vs premium requests).

Shared by email formatters, forecasts, and exports. Keeps billing fetch logic
in ``report_data`` / ``billing`` separate from presentation.
"""

from __future__ import annotations

from .report_helpers import fmt_price


def _effective_metering(copilot: dict) -> str:
    """Infer metering for cached reports that predate the ``metering`` field."""
    metering = copilot.get("metering")
    if metering in ("ai_credits", "premium_requests"):
        return metering
    if float(copilot.get("total_credits_used") or 0.0) > 0:
        return "ai_credits"
    if float(copilot.get("total_requests") or 0.0) > 0 or copilot.get("by_model"):
        return "premium_requests"
    return metering or "unknown"


def copilot_section_title(copilot: dict) -> str:
    """Heading for the Copilot usage block in reports."""
    metering = _effective_metering(copilot)
    if metering == "ai_credits":
        return "Copilot AI Credits"
    if metering == "premium_requests":
        return "Copilot Premium Requests"
    return "Copilot Usage"


def copilot_usage_summary_lines(copilot: dict) -> list[str]:
    """Primary Copilot usage bullets (metering-aware)."""
    lines: list[str] = []
    metering = _effective_metering(copilot)
    if metering == "ai_credits":
        credits_used = float(copilot.get("total_credits_used") or 0.0)
        lines.append(f"- AI credits used (quantity): {credits_used:,.2f}")
        billable = float(copilot.get("total_billable_credits") or 0.0)
        if billable > 0 and abs(billable - credits_used) > 0.001:
            lines.append(f"- Billable credits (net quantity): {billable:,.2f}")
    elif metering == "premium_requests":
        lines.append(f"- Total requests: {copilot.get('total_requests', 0.0):,.1f}")
    else:
        lines.append("- Usage metering could not be determined from billing APIs.")
    lines.append(
        f"- Net cost (Copilot product summary): {fmt_price(float(copilot.get('total_net', 0.0)))}"
    )
    note = copilot.get("usage_note")
    if note:
        lines.append(f"- Note: {note}")
    return lines


def copilot_model_detail_line(model: str, values: dict, *, metering: str) -> str:
    """One model line under the Copilot section."""
    effective = metering if metering in ("ai_credits", "premium_requests") else "premium_requests"
    if effective == "ai_credits":
        qty = float(values.get("requests", 0.0))
        return f"  - {model}: {qty:,.2f} credits (gross quantity)"
    requests = values.get("requests", values.get("total_requests", 0.0))
    return f"  - {model}: {float(requests):,.1f} requests"


def copilot_forecast_metric(copilot: dict) -> tuple[float, str]:
    """Return (current usage value, row label) for the usage forecast table."""
    metering = _effective_metering(copilot)
    if metering == "ai_credits":
        value = float(copilot.get("total_credits_used") or 0.0)
        return value, "AI Credits (qty)"
    if metering == "premium_requests":
        return float(copilot.get("total_requests") or 0.0), "Premium Requests"
    return 0.0, "Copilot usage"


def copilot_export_primary_row(copilot: dict) -> tuple[str, float]:
    """Primary usage label and value for PDF/XLSX Copilot summary sections."""
    value, label = copilot_forecast_metric(copilot)
    if label == "Premium Requests":
        return "Total Requests", value
    if label == "AI Credits (qty)":
        return "AI Credits Used (qty)", value
    return label, value


def copilot_by_model_quantity_header(copilot: dict) -> str:
    """Column header for per-model quantity in tabular exports."""
    if _effective_metering(copilot) == "ai_credits":
        return "Credits (qty)"
    return "Requests"
