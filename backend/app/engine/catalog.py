"""Field catalog: every fact about an application that a policy rule may test.

This is the single source of truth shared by the feature deriver (which must produce
every key), the rule validator (operator/value must suit the field type) and the policy
editor UI (dropdowns, input widgets, units).

Adding a new criterion = add a FieldDef here + produce the value in features.py.
"""

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class FieldType(StrEnum):
    NUMBER = "number"
    BOOLEAN = "boolean"
    ENUM = "enum"


class Unit(StrEnum):
    NONE = ""
    MONEY = "money"
    PERCENT = "percent"
    YEARS = "years"
    MONTHS = "months"
    MILES = "miles"
    SCORE = "score"
    COUNT = "count"


@dataclass(frozen=True)
class FieldDef:
    key: str
    label: str
    type: FieldType
    category: str
    unit: Unit = Unit.NONE
    options: tuple[str, ...] = ()
    derived: bool = False
    description: str = ""
    # How much room above a minimum counts as "maximum headroom" for the fit score.
    # None -> 25% of the threshold.
    headroom_span: float | None = None
    extra: dict[str, Any] = field(default_factory=dict)


US_STATES = (
    "AL", "AK", "AZ", "AR", "CA", "CO", "CT", "DE", "DC", "FL", "GA", "HI", "ID", "IL", "IN",
    "IA", "KS", "KY", "LA", "ME", "MD", "MA", "MI", "MN", "MS", "MO", "MT", "NE", "NV", "NH",
    "NJ", "NM", "NY", "NC", "ND", "OH", "OK", "OR", "PA", "RI", "SC", "SD", "TN", "TX", "UT",
    "VT", "VA", "WA", "WV", "WI", "WY",
)  # fmt: skip

INDUSTRIES = (
    "construction", "trucking", "logging", "manufacturing", "medical", "dental", "veterinary",
    "automotive_repair", "landscaping", "agriculture", "commercial_cleaning",
    "waste_management", "restaurant", "retail", "professional_services", "beauty_salon",
    "tattoo_piercing", "car_wash", "gaming_gambling", "adult_entertainment", "cannabis",
    "oil_gas", "real_estate", "money_services", "weapons_firearms", "church_nonprofit",
    "hazmat", "other",
)  # fmt: skip

EQUIPMENT_CATEGORIES = (
    "class_8_truck", "trailer", "reefer_trailer", "dump_truck", "medium_duty_truck",
    "light_duty_truck", "vocational_truck", "construction", "forklift", "material_handling",
    "machine_tools", "industrial_machinery", "woodworking", "medical", "automotive_repair",
    "landscaping", "farm", "janitorial", "restaurant", "office_copier", "audio_visual",
    "furniture", "signage", "kiosk", "atm", "aircraft_boat", "electric_vehicle",
    "tanning_bed", "logging", "leasehold_improvements", "software_soft_costs", "other",
)  # fmt: skip

ENTITY_TYPES = ("llc", "corporation", "s_corp", "partnership", "sole_proprietorship")
TRANSACTION_TYPES = ("dealer_purchase", "private_party", "sale_leaseback", "refinance")

_N, _B, _E = FieldType.NUMBER, FieldType.BOOLEAN, FieldType.ENUM

FIELDS: tuple[FieldDef, ...] = (
    # --- business
    FieldDef("business_state", "Business state", _E, "geography", options=US_STATES),
    FieldDef("industry", "Industry", _E, "industry", options=INDUSTRIES),
    FieldDef("entity_type", "Entity type", _E, "business", options=ENTITY_TYPES),
    FieldDef("years_in_business", "Time in business", _N, "business", Unit.YEARS, headroom_span=5),
    FieldDef("annual_revenue", "Annual revenue", _N, "business", Unit.MONEY),
    FieldDef("has_physical_location", "Has a physical location", _B, "business"),
    FieldDef("is_us_based", "US-based business", _B, "geography"),
    FieldDef("trucks_operated", "Trucks operated", _N, "business", Unit.COUNT, headroom_span=5),
    FieldDef("is_startup", "Start-up (under 2 years)", _B, "business", derived=True),
    FieldDef("is_trucking", "Trucking business", _B, "industry", derived=True),
    FieldDef("is_medical", "Medical practice", _B, "industry", derived=True),
    # --- guarantor (worst case across guarantors with >= 10% ownership)
    FieldDef("corp_only", "No personal guarantor (corp only)", _B, "guarantor"),
    FieldDef(
        "fico_score",
        "FICO score",
        _N,
        "credit",
        Unit.SCORE,
        headroom_span=60,
        description="Lowest score across guarantors.",
    ),
    FieldDef("is_homeowner", "Guarantor is a homeowner", _B, "guarantor"),
    FieldDef("years_at_residence", "Years at current residence", _N, "guarantor", Unit.YEARS),
    FieldDef("is_us_citizen", "All guarantors are US citizens", _B, "guarantor"),
    FieldDef(
        "industry_experience_years",
        "Industry experience",
        _N,
        "guarantor",
        Unit.YEARS,
        headroom_span=5,
    ),
    FieldDef("has_cdl", "Holds a CDL", _B, "guarantor"),
    FieldDef("cdl_years", "Years holding CDL", _N, "guarantor", Unit.YEARS),
    FieldDef("is_licensed_medical_professional", "Licensed medical professional", _B, "guarantor"),
    FieldDef("years_licensed", "Years licensed", _N, "guarantor", Unit.YEARS, headroom_span=5),
    FieldDef(
        "revolving_available_pct",
        "Revolving credit available",
        _N,
        "credit",
        Unit.PERCENT,
        derived=True,
        headroom_span=40,
    ),
    FieldDef("revolving_balance", "Personal revolving balance", _N, "credit", Unit.MONEY),
    FieldDef(
        "revolving_plus_unsecured_debt",
        "Revolving + unsecured debt",
        _N,
        "credit",
        Unit.MONEY,
        derived=True,
    ),
    # --- derogatory history (any guarantor)
    FieldDef("has_bankruptcy", "Bankruptcy on record", _B, "history"),
    FieldDef(
        "years_since_bankruptcy_discharge",
        "Years since bankruptcy discharge",
        _N,
        "history",
        Unit.YEARS,
        derived=True,
    ),
    FieldDef("has_judgments", "Judgments on record", _B, "history"),
    FieldDef("has_foreclosures", "Foreclosures on record", _B, "history"),
    FieldDef("has_repossessions", "Repossessions on record", _B, "history"),
    FieldDef("has_tax_liens", "Tax liens on record", _B, "history"),
    FieldDef("has_recent_collections", "Collections / charge-offs in last 3 years", _B, "history"),
    # --- business credit
    FieldDef("has_paynet", "PayNet score available", _B, "credit", derived=True),
    FieldDef("paynet_score", "PayNet MasterScore", _N, "credit", Unit.SCORE, headroom_span=60),
    FieldDef("trade_lines_count", "Trade lines", _N, "credit", Unit.COUNT),
    FieldDef("trade_history_years", "Trade history", _N, "credit", Unit.YEARS, headroom_span=5),
    FieldDef("largest_comparable_credit", "Largest comparable credit", _N, "credit", Unit.MONEY),
    FieldDef(
        "comparable_credit_pct",
        "Comparable credit vs. request",
        _N,
        "credit",
        Unit.PERCENT,
        derived=True,
        headroom_span=50,
    ),
    FieldDef(
        "comparable_contracts_count", "Comparable contracts (12 mo)", _N, "credit", Unit.COUNT
    ),
    FieldDef("clean_payment_history_months", "Clean payment history", _N, "credit", Unit.MONTHS),
    # --- loan request
    FieldDef("loan_amount", "Requested amount", _N, "loan", Unit.MONEY),
    FieldDef("term_months", "Requested term", _N, "loan", Unit.MONTHS),
    FieldDef("transaction_type", "Transaction type", _E, "loan", options=TRANSACTION_TYPES),
    FieldDef("down_payment_pct", "Down payment", _N, "loan", Unit.PERCENT),
    FieldDef("soft_cost_pct", "Soft costs", _N, "loan", Unit.PERCENT),
    # --- equipment (oldest / highest-mileage item)
    FieldDef("equipment_category", "Equipment type", _E, "equipment", options=EQUIPMENT_CATEGORIES),
    FieldDef("equipment_age_years", "Equipment age", _N, "equipment", Unit.YEARS, derived=True),
    FieldDef("equipment_mileage", "Equipment mileage", _N, "equipment", Unit.MILES),
    FieldDef(
        "equipment_condition", "Equipment condition", _E, "equipment", options=("new", "used")
    ),
    FieldDef("equipment_is_titled", "Titled equipment", _B, "equipment"),
)

CATALOG: dict[str, FieldDef] = {f.key: f for f in FIELDS}

CATEGORIES = (
    "credit", "business", "loan", "equipment", "geography", "industry", "history",
    "guarantor", "other",
)  # fmt: skip


def get_field(key: str) -> FieldDef:
    try:
        return CATALOG[key]
    except KeyError:
        raise KeyError(f"Unknown field '{key}'. Add it to app.engine.catalog.FIELDS.") from None
