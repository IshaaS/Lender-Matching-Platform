"""What an application needs before it can be underwritten. Returns every gap at once so the
UI can point at all of them, not just the first."""

from typing import Any

_MEDICAL = {"medical", "dental", "veterinary"}


def _missing(data: dict[str, Any], prefix: str, required: dict[str, str]) -> list[dict[str, str]]:
    return [
        {"path": f"{prefix}.{key}", "label": label}
        for key, label in required.items()
        if data.get(key) is None or data.get(key) == ""
    ]


def missing_fields(payload: dict[str, Any]) -> list[dict[str, str]]:
    business = payload.get("business") or {}
    loan = payload.get("loan") or {}
    corp_only = bool(loan.get("corp_only"))

    business_required = {
        "legal_name": "Business legal name",
        "state": "Business state",
        "industry": "Industry",
        "years_in_business": "Time in business",
        "has_physical_location": "Physical location",
        "is_us_based": "US-based business",
    }
    if business.get("industry") == "trucking":
        business_required["trucks_operated"] = "Trucks operated"
    if corp_only:
        business_required["annual_revenue"] = "Annual revenue (required for corp-only)"

    gaps = _missing(business, "business", business_required)
    gaps += _missing(
        loan,
        "loan",
        {
            "amount": "Requested amount",
            "term_months": "Requested term",
            "transaction_type": "Transaction type",
        },
    )
    gaps += _missing(
        payload.get("business_credit") or {},
        "business_credit",
        {
            "largest_comparable_credit": "Largest comparable credit (enter 0 if none)",
            "comparable_contracts_count": "Comparable contracts (enter 0 if none)",
        },
    )

    guarantors = payload.get("guarantors") or []
    if not corp_only:
        if not guarantors:
            gaps.append({"path": "guarantors", "label": "At least one personal guarantor"})
        for index, guarantor in enumerate(guarantors):
            required = {
                "full_name": "Guarantor name",
                "ownership_pct": "Ownership %",
                "fico_score": "FICO score",
                "is_homeowner": "Homeowner",
                "is_us_citizen": "US citizen",
                "revolving_credit_limit": "Revolving credit limit",
                "revolving_balance": "Revolving balance",
            }
            if business.get("industry") in _MEDICAL:
                required["is_licensed_medical_professional"] = "Licensed medical professional"
            gaps += _missing(guarantor, f"guarantors.{index}", required)

    equipment = payload.get("equipment") or []
    if not equipment:
        gaps.append({"path": "equipment", "label": "At least one equipment item"})
    for index, item in enumerate(equipment):
        gaps += _missing(
            item,
            f"equipment.{index}",
            {
                "category": "Equipment type",
                "model_year": "Model year",
                "condition": "Condition",
            },
        )
    return gaps
