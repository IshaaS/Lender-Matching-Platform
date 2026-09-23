"""Translation between the nested application payload and application rows."""

from typing import Any

from app.models import Business, BusinessCreditProfile, EquipmentItem, Guarantor, LoanApplication

_BUSINESS = ("legal_name", "entity_type", "state", "industry", "years_in_business",
             "annual_revenue", "has_physical_location", "is_us_based",
             "trucks_operated")  # fmt: skip
_LOAN = ("amount", "term_months", "transaction_type", "down_payment_pct", "soft_cost_pct",
         "corp_only", "notes")  # fmt: skip
_CREDIT = ("paynet_score", "trade_lines_count", "trade_history_years",
           "largest_comparable_credit", "comparable_contracts_count",
           "clean_payment_history_months")  # fmt: skip
_GUARANTOR = ("full_name", "ownership_pct", "fico_score", "is_homeowner", "years_at_residence",
              "is_us_citizen", "industry_experience_years", "has_cdl", "cdl_class", "cdl_years",
              "is_licensed_medical_professional", "years_licensed", "revolving_credit_limit",
              "revolving_balance", "unsecured_debt", "has_bankruptcy",
              "bankruptcy_discharge_date", "has_judgments", "has_foreclosures",
              "has_repossessions", "has_tax_liens", "has_recent_collections")  # fmt: skip
_EQUIPMENT = ("category", "description", "model_year", "condition", "mileage", "hours",
              "is_titled")  # fmt: skip


def _pick(data: dict[str, Any] | None, keys: tuple[str, ...]) -> dict[str, Any]:
    return {k: v for k, v in (data or {}).items() if k in keys and v is not None}


def _dump(row: Any, keys: tuple[str, ...]) -> dict[str, Any]:
    return {k: getattr(row, k) for k in keys}


def apply_payload(application: LoanApplication, payload: dict[str, Any]) -> LoanApplication:
    """Replace the application's content with the payload (children are rebuilt)."""
    if application.business is None:
        application.business = Business()
    for key in _BUSINESS:
        setattr(application.business, key, (payload.get("business") or {}).get(key))
    loan = payload.get("loan") or {}
    for key in _LOAN:
        setattr(application, key, loan.get(key))
    application.corp_only = bool(loan.get("corp_only"))

    # One-to-one rows are updated in place: replacing them would INSERT before DELETE and
    # trip the unique constraint on application_id.
    if application.business_credit is None:
        application.business_credit = BusinessCreditProfile()
    for key in _CREDIT:
        setattr(application.business_credit, key, (payload.get("business_credit") or {}).get(key))
    application.guarantors = [
        Guarantor(**_pick(g, _GUARANTOR)) for g in payload.get("guarantors") or []
    ]
    application.equipment_items = [
        EquipmentItem(**_pick(e, _EQUIPMENT)) for e in payload.get("equipment") or []
    ]
    return application


def to_payload(application: LoanApplication) -> dict[str, Any]:
    return {
        "business": _dump(application.business, _BUSINESS),
        "loan": _dump(application, _LOAN),
        "business_credit": (
            _dump(application.business_credit, _CREDIT)
            if application.business_credit
            else dict.fromkeys(_CREDIT)
        ),
        "guarantors": [_dump(g, _GUARANTOR) for g in application.guarantors],
        "equipment": [_dump(e, _EQUIPMENT) for e in application.equipment_items],
    }
