"""Demo applications. Shapes match the application API payload, so the same data seeds the
database, backs the UI's "load sample" buttons and drives the golden tests."""

from typing import Any

Json = dict[str, Any]


def _guarantor(**overrides: Any) -> Json:
    base: Json = {
        "full_name": "Alex Morgan", "ownership_pct": 100, "fico_score": 720,
        "is_homeowner": True, "years_at_residence": 8, "is_us_citizen": True,
        "industry_experience_years": 10, "has_cdl": False, "cdl_class": None, "cdl_years": None,
        "is_licensed_medical_professional": False, "years_licensed": None,
        "revolving_credit_limit": 40000, "revolving_balance": 8000, "unsecured_debt": 5000,
        "has_bankruptcy": False, "bankruptcy_discharge_date": None, "has_judgments": False,
        "has_foreclosures": False, "has_repossessions": False, "has_tax_liens": False,
        "has_recent_collections": False,
    }  # fmt: skip
    return {**base, **overrides}


STRONG: Json = {
    "key": "strong",
    "title": "Strong - established contractor",
    "business": {
        "legal_name": "Lone Star Excavation LLC", "entity_type": "llc", "state": "TX",
        "industry": "construction", "years_in_business": 8, "annual_revenue": 2400000,
        "has_physical_location": True, "is_us_based": True, "trucks_operated": None,
    },
    "loan": {"amount": 120000, "term_months": 60, "transaction_type": "dealer_purchase",
             "down_payment_pct": 10, "soft_cost_pct": 5, "corp_only": False},
    "business_credit": {"paynet_score": 700, "trade_lines_count": 9, "trade_history_years": 9,
                        "largest_comparable_credit": 120000, "comparable_contracts_count": 4,
                        "clean_payment_history_months": 36},
    "guarantors": [_guarantor(full_name="Dana Whitfield", fico_score=760,
                              industry_experience_years=12)],
    "equipment": [{"category": "construction", "description": "Compact excavator",
                   "model_year": 2025, "condition": "new", "mileage": None, "hours": 0,
                   "is_titled": False}],
}  # fmt: skip

MARGINAL: Json = {
    "key": "marginal",
    "title": "Marginal - young landscaping business",
    "business": {
        "legal_name": "Buckeye Lawn & Landscape Inc", "entity_type": "s_corp", "state": "OH",
        "industry": "landscaping", "years_in_business": 2.5, "annual_revenue": 380000,
        "has_physical_location": True, "is_us_based": True, "trucks_operated": None,
    },
    "loan": {"amount": 60000, "term_months": 48, "transaction_type": "dealer_purchase",
             "down_payment_pct": 10, "soft_cost_pct": 0, "corp_only": False},
    "business_credit": {"paynet_score": 655, "trade_lines_count": 3, "trade_history_years": 3,
                        "largest_comparable_credit": 30000, "comparable_contracts_count": 1,
                        "clean_payment_history_months": 14},
    "guarantors": [_guarantor(full_name="Chris Patel", fico_score=685, is_homeowner=False,
                              years_at_residence=3, industry_experience_years=6,
                              revolving_credit_limit=20000, revolving_balance=12000,
                              unsecured_debt=8000)],
    "equipment": [{"category": "landscaping", "description": "Zero-turn mower fleet",
                   "model_year": 2024, "condition": "used", "mileage": None, "hours": 450,
                   "is_titled": False}],
}  # fmt: skip

TRUCKING: Json = {
    "key": "trucking",
    "title": "Trucking - 8-truck fleet adding a tractor",
    "business": {
        "legal_name": "Peach State Freight LLC", "entity_type": "llc", "state": "GA",
        "industry": "trucking", "years_in_business": 7, "annual_revenue": 1900000,
        "has_physical_location": True, "is_us_based": True, "trucks_operated": 8,
    },
    "loan": {"amount": 140000, "term_months": 48, "transaction_type": "dealer_purchase",
             "down_payment_pct": 10, "soft_cost_pct": 0, "corp_only": False},
    "business_credit": {"paynet_score": 690, "trade_lines_count": 7, "trade_history_years": 6,
                        "largest_comparable_credit": 140000, "comparable_contracts_count": 5,
                        "clean_payment_history_months": 30},
    "guarantors": [_guarantor(full_name="Marcus Reed", fico_score=715, has_cdl=True,
                              cdl_class="A", cdl_years=10, revolving_credit_limit=30000,
                              revolving_balance=9000)],
    "equipment": [{"category": "class_8_truck", "description": "Freightliner Cascadia",
                   "model_year": 2021, "condition": "used", "mileage": 380000, "hours": None,
                   "is_titled": True}],
}  # fmt: skip

STARTUP: Json = {
    "key": "startup",
    "title": "Start-up - new dental practice",
    "business": {
        "legal_name": "Gulf Coast Family Dental PLLC", "entity_type": "llc", "state": "FL",
        "industry": "dental", "years_in_business": 1, "annual_revenue": 450000,
        "has_physical_location": True, "is_us_based": True, "trucks_operated": None,
    },
    "loan": {"amount": 45000, "term_months": 60, "transaction_type": "dealer_purchase",
             "down_payment_pct": 20, "soft_cost_pct": 10, "corp_only": False},
    "business_credit": {"paynet_score": None, "trade_lines_count": 1, "trade_history_years": 1,
                        "largest_comparable_credit": 20000, "comparable_contracts_count": 0,
                        "clean_payment_history_months": 10},
    "guarantors": [_guarantor(full_name="Dr. Priya Nair", fico_score=735,
                              industry_experience_years=6,
                              is_licensed_medical_professional=True, years_licensed=6,
                              revolving_credit_limit=25000, revolving_balance=5000,
                              unsecured_debt=0)],
    "equipment": [{"category": "medical", "description": "Digital X-ray + operatory chairs",
                   "model_year": 2025, "condition": "new", "mileage": None, "hours": None,
                   "is_titled": False}],
}  # fmt: skip

SAMPLES: tuple[Json, ...] = (STRONG, MARGINAL, TRUCKING, STARTUP)
