"""Turns a raw application into the flat feature set that rules are evaluated against.

Every key in the catalog is produced here (value may be None when not provided).
"""

from datetime import date
from typing import Any

from pydantic import BaseModel, Field

from app.engine.catalog import CATALOG

FeatureSet = dict[str, Any]

STARTUP_THRESHOLD_YEARS = 2
# Owners below this stake do not have to guarantee (Citizens: "at least 10% ownership must PG").
GUARANTOR_OWNERSHIP_THRESHOLD = 10
TRUCKING_INDUSTRIES = {"trucking"}
MEDICAL_INDUSTRIES = {"medical", "dental", "veterinary"}


class GuarantorInput(BaseModel):
    ownership_pct: float | None = None
    fico_score: int | None = None
    is_homeowner: bool | None = None
    years_at_residence: float | None = None
    is_us_citizen: bool | None = None
    industry_experience_years: float | None = None
    has_cdl: bool | None = None
    cdl_years: float | None = None
    is_licensed_medical_professional: bool | None = None
    years_licensed: float | None = None
    revolving_credit_limit: float | None = None
    revolving_balance: float | None = None
    unsecured_debt: float | None = None
    has_bankruptcy: bool = False
    bankruptcy_discharge_date: date | None = None
    has_judgments: bool = False
    has_foreclosures: bool = False
    has_repossessions: bool = False
    has_tax_liens: bool = False
    has_recent_collections: bool = False


class EquipmentInput(BaseModel):
    category: str | None = None
    model_year: int | None = None
    condition: str | None = None
    mileage: int | None = None
    is_titled: bool | None = None


class ApplicationInput(BaseModel):
    # business
    business_state: str | None = None
    industry: str | None = None
    entity_type: str | None = None
    years_in_business: float | None = None
    annual_revenue: float | None = None
    has_physical_location: bool | None = None
    is_us_based: bool | None = None
    trucks_operated: int | None = None
    # loan
    loan_amount: float | None = None
    term_months: int | None = None
    transaction_type: str | None = None
    down_payment_pct: float | None = None
    soft_cost_pct: float | None = None
    corp_only: bool = False
    # business credit
    paynet_score: int | None = None
    trade_lines_count: int | None = None
    trade_history_years: float | None = None
    largest_comparable_credit: float | None = None
    comparable_contracts_count: int | None = None
    clean_payment_history_months: int | None = None

    guarantors: list[GuarantorInput] = Field(default_factory=list)
    equipment: list[EquipmentInput] = Field(default_factory=list)


def _min(values: list[Any]) -> Any:
    present = [v for v in values if v is not None]
    return min(present) if present else None


def _max(values: list[Any]) -> Any:
    present = [v for v in values if v is not None]
    return max(present) if present else None


def _all_true(values: list[bool | None]) -> bool | None:
    """True only when every guarantor confirms; None when nobody answered."""
    present = [v for v in values if v is not None]
    return all(present) if present else None


def _sum(values: list[float | None]) -> float | None:
    present = [v for v in values if v is not None]
    return sum(present) if present else None


def _years_between(earlier: date, later: date) -> float:
    return round((later - earlier).days / 365.25, 1)


def derive_features(app: ApplicationInput, today: date | None = None) -> FeatureSet:
    today = today or date.today()
    # Multiple guarantors collapse to the worst case: lenders underwrite to the weakest PG.
    gs = [
        g
        for g in app.guarantors
        if g.ownership_pct is None or g.ownership_pct >= GUARANTOR_OWNERSHIP_THRESHOLD
    ] or app.guarantors

    limit = _sum([g.revolving_credit_limit for g in gs])
    balance = _sum([g.revolving_balance for g in gs])
    unsecured = _sum([g.unsecured_debt for g in gs])
    revolving_available_pct = (
        round((1 - (balance or 0) / limit) * 100, 1) if limit and limit > 0 else None
    )

    discharge_dates = [g.bankruptcy_discharge_date for g in gs if g.has_bankruptcy]
    has_bankruptcy = any(g.has_bankruptcy for g in gs)
    years_since_discharge: float | None = None
    if has_bankruptcy:
        # An undischarged bankruptcy counts as zero years.
        years_since_discharge = (
            0.0
            if any(d is None for d in discharge_dates)
            else _years_between(max(d for d in discharge_dates if d), today)
        )

    model_years = [e.model_year for e in app.equipment if e.model_year]
    equipment_age = max(0, today.year - min(model_years)) if model_years else None
    primary = app.equipment[0] if app.equipment else EquipmentInput()

    comparable_pct = (
        round(app.largest_comparable_credit / app.loan_amount * 100, 1)
        if app.largest_comparable_credit is not None and app.loan_amount
        else None
    )

    features: FeatureSet = {
        "business_state": app.business_state,
        "industry": app.industry,
        "entity_type": app.entity_type,
        "years_in_business": app.years_in_business,
        "annual_revenue": app.annual_revenue,
        "has_physical_location": app.has_physical_location,
        "is_us_based": app.is_us_based,
        "trucks_operated": app.trucks_operated,
        "is_startup": (
            app.years_in_business < STARTUP_THRESHOLD_YEARS
            if app.years_in_business is not None
            else None
        ),
        "is_trucking": app.industry in TRUCKING_INDUSTRIES if app.industry else None,
        "is_medical": app.industry in MEDICAL_INDUSTRIES if app.industry else None,
        "corp_only": app.corp_only,
        "fico_score": _min([g.fico_score for g in gs]),
        "is_homeowner": _all_true([g.is_homeowner for g in gs]),
        "years_at_residence": _min([g.years_at_residence for g in gs]),
        "is_us_citizen": _all_true([g.is_us_citizen for g in gs]),
        "industry_experience_years": _max([g.industry_experience_years for g in gs]),
        "has_cdl": any(g.has_cdl for g in gs) if gs else None,
        "cdl_years": _max([g.cdl_years for g in gs]),
        "is_licensed_medical_professional": (
            any(g.is_licensed_medical_professional for g in gs) if gs else None
        ),
        "years_licensed": _max([g.years_licensed for g in gs]),
        "revolving_available_pct": revolving_available_pct,
        "revolving_balance": balance,
        "revolving_plus_unsecured_debt": (
            (balance or 0) + (unsecured or 0)
            if balance is not None or unsecured is not None
            else None
        ),
        "has_bankruptcy": has_bankruptcy,
        "years_since_bankruptcy_discharge": years_since_discharge,
        "has_judgments": any(g.has_judgments for g in gs),
        "has_foreclosures": any(g.has_foreclosures for g in gs),
        "has_repossessions": any(g.has_repossessions for g in gs),
        "has_tax_liens": any(g.has_tax_liens for g in gs),
        "has_recent_collections": any(g.has_recent_collections for g in gs),
        "has_paynet": app.paynet_score is not None,
        "paynet_score": app.paynet_score,
        "trade_lines_count": app.trade_lines_count,
        "trade_history_years": app.trade_history_years,
        "largest_comparable_credit": app.largest_comparable_credit,
        "comparable_credit_pct": comparable_pct,
        "comparable_contracts_count": app.comparable_contracts_count,
        "clean_payment_history_months": app.clean_payment_history_months,
        "loan_amount": app.loan_amount,
        "term_months": app.term_months,
        "transaction_type": app.transaction_type,
        "down_payment_pct": app.down_payment_pct,
        "soft_cost_pct": app.soft_cost_pct,
        "equipment_category": primary.category,
        "equipment_age_years": equipment_age,
        "equipment_mileage": _max([e.mileage for e in app.equipment]),
        "equipment_condition": primary.condition,
        "equipment_is_titled": (
            _all_true([e.is_titled for e in app.equipment]) if app.equipment else None
        ),
        "_equipment_list": [
            {
                "category": e.category,
                "age_years": (max(0, today.year - e.model_year) if e.model_year else None),
                "mileage": e.mileage,
                "condition": e.condition,
                "is_titled": e.is_titled,
            }
            for e in app.equipment
        ],
    }

    missing = CATALOG.keys() - (features.keys() - {"_equipment_list"})
    assert not missing, f"derive_features does not produce catalog fields: {sorted(missing)}"
    return features
