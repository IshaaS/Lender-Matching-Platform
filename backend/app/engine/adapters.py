"""Builds the engine's ApplicationInput from the nested application payload shape
(business / loan / business_credit / guarantors / equipment)."""

from typing import Any

from app.engine.features import ApplicationInput


def application_input_from_payload(payload: dict[str, Any]) -> ApplicationInput:
    business = dict(payload.get("business") or {})
    loan = dict(payload.get("loan") or {})
    return ApplicationInput.model_validate(
        {
            **business,
            "business_state": business.get("state"),
            **(payload.get("business_credit") or {}),
            **loan,
            "loan_amount": loan.get("amount"),
            "corp_only": bool(loan.get("corp_only")),
            "guarantors": [] if loan.get("corp_only") else payload.get("guarantors") or [],
            "equipment": payload.get("equipment") or [],
        }
    )
