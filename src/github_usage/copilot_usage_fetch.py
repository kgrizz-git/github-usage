"""Select Copilot usage source (AI credits vs premium requests) from billing APIs."""

from __future__ import annotations

from .billing import fetch_metered_billing_usage


def _billing_usage_has_items(by_model: dict | None) -> bool:
    if not by_model:
        return False
    return any(entry.get("items") for entry in by_model.values())


def resolve_copilot_usage_sources(
    api,
    username: str,
) -> tuple[str, dict, list[str]]:
    """Return ``(metering, raw_by_model, notes)`` for Copilot usage line items.

    Raises ``RuntimeError`` when both usage endpoints fail. Partial failures are
    recorded in ``notes`` while still allowing the working endpoint to supply data.
    """
    ai_raw, ai_err = fetch_metered_billing_usage(
        api, username, "ai_credit", product="copilot"
    )
    prem_raw, prem_err = fetch_metered_billing_usage(
        api, username, "premium_request", product="copilot"
    )

    if ai_err and prem_err:
        raise RuntimeError(
            "Copilot usage unavailable: "
            f"AI credit endpoint failed ({ai_err}); "
            f"premium request endpoint failed ({prem_err})"
        )

    notes: list[str] = []
    if ai_err:
        notes.append(f"AI credit usage unavailable ({ai_err})")
    if prem_err:
        notes.append(f"Premium request usage unavailable ({prem_err})")

    ai_data = ai_raw if ai_err is None else {}
    prem_data = prem_raw if prem_err is None else {}

    if ai_err is None and _billing_usage_has_items(ai_data):
        return "ai_credits", ai_data, notes
    if prem_err is None and _billing_usage_has_items(prem_data):
        return "premium_requests", prem_data, notes
    if ai_err is None and prem_err is None:
        return "ai_credits", {}, notes
    if prem_err is None:
        return "premium_requests", prem_data, notes
    if ai_err is None:
        return "ai_credits", ai_data, notes
    return "unknown", {}, notes
