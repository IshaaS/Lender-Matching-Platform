"""Tiny helpers that keep the policy definitions readable. They only build dicts that
are validated by app.engine.policy - there is no logic here."""

from typing import Any

Json = dict[str, Any]


def when(field: str, operator: str, value: Any = None) -> Json:
    return {"field": field, "operator": operator, "value": value}


def rule(
    label: str,
    category: str,
    field: str,
    operator: str,
    value: Any = None,
    *,
    soft: bool = False,
    applies_when: list[Json] | None = None,
    message: str | None = None,
) -> Json:
    return {
        "kind": "simple",
        "label": label,
        "category": category,
        "severity": "soft" if soft else "hard",
        "field": field,
        "operator": operator,
        "value": value,
        "applies_when": applies_when or [],
        "message_template": message,
    }


def any_of(
    label: str,
    category: str,
    alternatives: list[Json],
    *,
    soft: bool = False,
    applies_when: list[Json] | None = None,
) -> Json:
    return {
        "kind": "any_of",
        "label": label,
        "category": category,
        "severity": "soft" if soft else "hard",
        "alternatives": alternatives,
        "applies_when": applies_when or [],
    }


def alt(field: str, operator: str, value: Any, label: str) -> Json:
    return {"field": field, "operator": operator, "value": value, "label": label}


def program(
    name: str,
    rank: int,
    rules: list[Json],
    *,
    decision_mode: str = "automatic",
    applies_when: list[Json] | None = None,
    description: str | None = None,
    details: Json | None = None,
) -> Json:
    return {
        "name": name,
        "rank": rank,
        "decision_mode": decision_mode,
        "description": description,
        "applies_when": applies_when or [],
        "rules": rules,
        "details": details or {},
    }


# Shared building blocks -----------------------------------------------------------------

HAS_PG = when("corp_only", "is_false")
CORP_ONLY = when("corp_only", "is_true")
HAS_BANKRUPTCY = when("has_bankruptcy", "is_true")


def min_fico(score: int) -> Json:
    return rule("Minimum FICO", "credit", "fico_score", "gte", score)


def min_paynet(score: int) -> Json:
    return rule("Minimum PayNet", "credit", "paynet_score", "gte", score)


def min_tib(years: float) -> Json:
    return rule("Minimum time in business", "business", "years_in_business", "gte", years)


def pg_required() -> Json:
    return rule(
        "Personal guarantee required", "guarantor", "corp_only", "is_false",
        message="This lender requires a personal guarantee; corp-only requests are not accepted.",
    )  # fmt: skip


def bankruptcy_seasoning(years: int) -> Json:
    return rule(
        f"No bankruptcy in last {years} years", "history",
        "years_since_bankruptcy_discharge", "gte", years, applies_when=[HAS_BANKRUPTCY],
    )  # fmt: skip
