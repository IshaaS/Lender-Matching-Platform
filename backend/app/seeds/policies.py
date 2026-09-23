"""The five provided lender guideline PDFs, normalised into policy data.

Each function returns {"lender": {...}, "policy": {...}}. Every modelling judgement that is
not a literal reading of the PDF is marked ASSUMPTION and mirrored in DECISIONS.md.
"""

from app.seeds.builders import (
    CORP_ONLY,
    HAS_PG,
    Json,
    alt,
    any_of,
    bankruptcy_seasoning,
    min_fico,
    min_paynet,
    min_tib,
    pg_required,
    program,
    rule,
    when,
)

# ----------------------------------------------------------------------------------------
# Stearns Bank - "EF Credit Box 4.14.2025.pdf"
# ----------------------------------------------------------------------------------------


def stearns() -> Json:
    def family(
        suffix: str, rank_offset: int, applies: list[Json], tiers: list[list[Json]]
    ) -> list[Json]:
        return [
            program(
                f"Tier {i}{suffix}",
                rank_offset + i,
                rules,
                applies_when=applies,
                details={"note": "Guidelines only; subject to lender discretion."},
            )
            for i, rules in enumerate(tiers, start=1)
        ]

    has_paynet, no_paynet = when("has_paynet", "is_true"), when("has_paynet", "is_false")
    programs = [
        *family("", 0, [HAS_PG, has_paynet], [
            [min_fico(725), min_tib(3), min_paynet(685)],
            [min_fico(710), min_tib(3), min_paynet(675)],
            [min_fico(700), min_tib(2), min_paynet(665)],
        ]),
        *family(" (No PayNet)", 3, [HAS_PG, no_paynet], [
            [min_fico(735), min_tib(5)],
            [min_fico(720), min_tib(3)],
            [min_fico(710), min_tib(2)],
        ]),
        *family(" (Corp Only)", 6, [CORP_ONLY], [
            [min_paynet(700), min_tib(10)],
            [min_paynet(690), min_tib(5)],
            [min_paynet(680), min_tib(5)],
        ]),
    ]  # fmt: skip

    return {
        "lender": {"name": "Stearns Bank", "slug": "stearns-bank"},
        "policy": {
            "source_document": "EF Credit Box 4.14.2025.pdf",
            "rules": [
                rule(
                    "Restricted industries", "industry", "industry", "not_in",
                    ["gaming_gambling", "hazmat", "oil_gas", "money_services",
                     "adult_entertainment", "real_estate", "weapons_firearms", "beauty_salon",
                     "tattoo_piercing", "restaurant", "car_wash", "trucking"],
                    # ASSUMPTION: "OTR" (over-the-road) is mapped to the trucking industry.
                ),
                rule("Restricted equipment", "equipment", "equipment_category", "not_in",
                     ["tanning_bed"]),
                rule("US-based business", "geography", "is_us_based", "is_true"),
                rule("Physical business location", "business", "has_physical_location",
                     "is_true"),
                bankruptcy_seasoning(7),
                any_of("Comparable debt", "credit", [
                    alt("comparable_credit_pct", "gte", 100,
                        "a single open or recently closed account at least the size of the "
                        "request"),
                    alt("comparable_contracts_count", "gte", 3,
                        "3+ contracts ($10K minimum) with payment activity in the last 12 "
                        "months"),
                ]),
                # ASSUMPTION: the "Revolver Utilization" comment is read as two ceilings.
                rule("Personal revolving debt ceiling", "credit", "revolving_balance", "lte",
                     30000, applies_when=[HAS_PG]),
                rule("Revolving + unsecured debt ceiling", "credit",
                     "revolving_plus_unsecured_debt", "lte", 50000, applies_when=[HAS_PG]),
            ],
            "programs": programs,
        },
    }  # fmt: skip


# ----------------------------------------------------------------------------------------
# Apex Commercial Capital - "Apex EF Broker Guidelines_082725.pdf"
# ----------------------------------------------------------------------------------------


def apex() -> Json:
    revolving = rule("Revolving credit available", "credit", "revolving_available_pct", "gte", 50)

    def max_amount(amount: int) -> Json:
        return rule("Program maximum", "loan", "loan_amount", "lte", amount)

    def rates(small: str, large: str, large_band: str, app_only: str | None) -> Json:
        details: Json = {"rates": {"$10,000 - $49,999": small, large_band: large},
                         "term": "24-60 months"}  # fmt: skip
        if app_only:
            details["app_only_up_to"] = app_only
            details["above_app_only"] = (
                "2 years tax returns or accountant-prepared financials + 3 months bank statements"
            )
        return details

    medical = when("is_medical", "is_true")
    licensed = rule("Owned by licensed practitioner", "guarantor",
                    "is_licensed_medical_professional", "is_true")  # fmt: skip

    return {
        "lender": {
            "name": "Apex Commercial Capital",
            "slug": "apex-commercial-capital",
            "contact_email": "credit@apexcommercial.com",
        },
        "policy": {
            "source_document": "Apex EF Broker Guidelines_082725.pdf",
            "rules": [
                rule("Excluded states", "geography", "business_state", "not_in",
                     ["CA", "NV", "ND", "VT"],
                     message="Apex does not lend in {actual} (excluded: {expected})."),
                rule("Excluded industries", "industry", "industry", "not_in",
                     ["cannabis", "gaming_gambling", "church_nonprofit", "oil_gas", "trucking",
                      "logging", "beauty_salon"]),
                rule("Excluded equipment", "equipment", "equipment_category", "not_in",
                     ["aircraft_boat", "atm", "audio_visual", "office_copier",
                      "electric_vehicle", "furniture", "kiosk", "leasehold_improvements",
                      "logging", "signage", "tanning_bed"]),
                rule("Maximum equipment age", "equipment", "equipment_age_years", "lte", 15),
                rule("No private party sales or sale-leasebacks", "loan", "transaction_type",
                     "not_in", ["private_party", "sale_leaseback"]),
                rule("Financing range", "loan", "loan_amount", "between", [10000, 500000]),
                rule("Term range", "loan", "term_months", "between", [24, 60]),
                rule("Maximum soft costs", "loan", "soft_cost_pct", "lte", 25),
                rule("Comparable borrowing (50%) for $50K-$100K", "credit",
                     "comparable_credit_pct", "gte", 50,
                     applies_when=[when("loan_amount", "between", [50000, 100000])]),
                rule("Comparable borrowing (75%) over $100K", "credit",
                     "comparable_credit_pct", "gte", 75,
                     applies_when=[when("loan_amount", "gt", 100000)]),
            ],
            "programs": [
                program("A+ Rate", 1, [
                    min_tib(5), min_paynet(670), min_fico(720), revolving,
                    rule("Maximum collateral age", "equipment", "equipment_age_years", "lte", 5),
                    any_of("Eligible industry or equipment", "industry", [
                        alt("industry", "in",
                            ["landscaping", "automotive_repair", "construction",
                             "commercial_cleaning", "manufacturing", "medical", "dental",
                             "veterinary", "waste_management"], "an A+ eligible industry"),
                        alt("equipment_category", "in",
                            ["forklift", "industrial_machinery", "machine_tools",
                             "vocational_truck", "construction", "landscaping",
                             "automotive_repair", "medical"], "an A+ eligible equipment type"),
                    ]),
                ], applies_when=[HAS_PG],
                    details=rates("6.75%", "6.50%", "$50,000 - $500,000", "$200,000")),
                program("Medical A Rate", 2, [
                    licensed,
                    rule("Minimum time licensed", "guarantor", "years_licensed", "gte", 5),
                    min_fico(700), revolving,
                ], applies_when=[HAS_PG, medical],
                    details=rates("7.25%", "7.00%", "$50,000 - $500,000", "$200,000")),
                program("A Rate", 3, [min_tib(5), min_paynet(660), min_fico(700), revolving],
                        applies_when=[HAS_PG],
                        details=rates("7.75%", "7.25%", "$50,000 - $500,000", "$200,000")),
                program("Medical B Rate", 4, [
                    licensed,
                    rule("Minimum time licensed", "guarantor", "years_licensed", "gte", 2),
                    min_fico(670), revolving, max_amount(250000),
                ], applies_when=[HAS_PG, medical],
                    details=rates("8.00%", "7.50%", "$50,000 - $250,000", "$100,000")),
                program("B Rate", 5, [
                    min_tib(3), min_paynet(650), min_fico(670), revolving, max_amount(250000),
                ], applies_when=[HAS_PG],
                    details=rates("8.75%", "8.25%", "$50,000 - $250,000", "$100,000")),
                program("C Rate", 6, [
                    min_tib(2), min_paynet(640), min_fico(640), max_amount(100000),
                ], applies_when=[HAS_PG],
                    details={**rates("12.00%", "11.00%", "$50,000 - $100,000", None),
                             "documents": "3 months bank statements with submission"}),
                program("Corp Only", 7, [
                    min_tib(5),
                    rule("Minimum annual sales", "business", "annual_revenue", "gte", 3000000),
                    rule("Comparable business credit (75%)", "credit", "comparable_credit_pct",
                         "gte", 75),
                ], applies_when=[CORP_ONLY],
                    details={"buy_rate": "7.00%",
                             "documents": "2 years business tax returns or accountant-prepared "
                                          "financials; 3 months business bank statements"}),
            ],
        },
    }  # fmt: skip


# ----------------------------------------------------------------------------------------
# Advantage+ Financing - "Advantage++Broker+2025.pdf" (non-trucking, up to $75K)
# ----------------------------------------------------------------------------------------


def advantage_plus() -> Json:
    def clean(label: str, field: str) -> Json:
        return rule(label, "history", field, "is_false")

    return {
        "lender": {
            "name": "Advantage+ Financing",
            "slug": "advantage-plus-financing",
            "contact_email": "SalesSupport@advantageplusfinancing.com",
            "contact_phone": "(262) 439-7600",
        },
        "policy": {
            "source_document": "Advantage++Broker+2025.pdf",
            "rules": [
                pg_required(),
                rule("Non-trucking applications only", "industry", "is_trucking", "is_false",
                     message="This program is for non-trucking applications only."),
                rule("Loan amount range", "loan", "loan_amount", "between", [10000, 75000]),
                rule("Maximum term", "loan", "term_months", "lte", 60),
                rule("US citizens only", "guarantor", "is_us_citizen", "is_true"),
                rule("Minimum industry experience", "guarantor", "industry_experience_years",
                     "gte", 3),
                clean("No bankruptcies", "has_bankruptcy"),
                clean("No judgments", "has_judgments"),
                clean("No foreclosures", "has_foreclosures"),
                clean("No repossessions", "has_repossessions"),
                clean("No tax liens", "has_tax_liens"),
                clean("No collections or charge-offs in past 3 years", "has_recent_collections"),
                # "Prefer ..." in the PDF -> soft: lowers the fit score, never rejects.
                rule("Prefers 7 years' trade history", "credit", "trade_history_years", "gte", 7,
                     soft=True),
                rule("Prefers 80% comparable credit", "credit", "comparable_credit_pct", "gte",
                     80, soft=True),
            ],
            "programs": [
                program("Established Business", 1, [
                    rule("Minimum FICO (v5 Equifax)", "credit", "fico_score", "gte", 680),
                    rule("Typical minimum down payment", "loan", "down_payment_pct", "gte", 10,
                         soft=True),
                ], applies_when=[when("is_startup", "is_false")],
                    details={"credit_range": "A to B-", "decision_time": "1 business day",
                             "documents": "May need 4 months' bank statements and/or PFS"}),
                program("Start-Up", 2, [
                    rule("Minimum FICO for start-ups", "credit", "fico_score", "gte", 700),
                    rule("Down payment + security deposit", "loan", "down_payment_pct", "gte",
                         20, soft=True),
                ], applies_when=[when("is_startup", "is_true")],
                    details={"documents": "Prior year personal tax return likely required",
                             "note": "10% down plus additional 10% security deposit"}),
            ],
        },
    }  # fmt: skip


# ----------------------------------------------------------------------------------------
# Citizens Bank - "2025 Program Guidelines UPDATED.pdf"
# ----------------------------------------------------------------------------------------


def citizens() -> Json:
    cdl_equipment = ["class_8_truck", "dump_truck", "medium_duty_truck"]
    transunion_700 = rule("Minimum credit score (TransUnion)", "credit", "fico_score", "gte", 700)
    app_only_docs = "3 months bank statements"

    def max_term(months: int, older_than: int) -> Json:
        return rule(
            f"Maximum term for equipment over {older_than} years old", "equipment",
            "term_months", "lte", months,
            applies_when=[when("equipment_age_years", "gt", older_than)],
        )  # fmt: skip

    return {
        "lender": {
            "name": "Citizens Bank",
            "slug": "citizens-bank",
            "contact_name": "Joey Walter",
            "contact_email": "joey.walter@thecitizensbank.net",
            "contact_phone": "501-451-5113",
        },
        "policy": {
            "source_document": "2025 Program Guidelines UPDATED.pdf",
            "rules": [
                pg_required(),
                rule("Excluded states", "geography", "business_state", "not_in", ["CA"],
                     message="Citizens Bank no longer finances applicants in {actual}."),
                rule("Excluded industries", "industry", "industry", "not_in", ["cannabis"]),
                rule("US citizens only", "guarantor", "is_us_citizen", "is_true"),
                bankruptcy_seasoning(5),
                rule("No sale-leaseback or refinance", "loan", "transaction_type", "not_in",
                     ["sale_leaseback", "refinance"]),
                rule("Private party only on titled equipment", "equipment",
                     "equipment_is_titled", "is_true",
                     applies_when=[when("transaction_type", "eq", "private_party")]),
                any_of("CDL or 10+ unit fleet for CDL equipment", "guarantor", [
                    alt("has_cdl", "is_true", None, "an owner holding a CDL"),
                    alt("trucks_operated", "gte", 10, "a fleet of at least 10 units"),
                ], applies_when=[when("equipment_category", "in", cdl_equipment)]),
                rule("Medical equipment requires a medical doctor", "guarantor",
                     "is_licensed_medical_professional", "is_true",
                     applies_when=[when("equipment_category", "eq", "medical")]),
                rule("Maximum transaction size", "loan", "loan_amount", "lte", 1000000),
                rule("Maximum term", "loan", "term_months", "lte", 60),
                # ASSUMPTION: the per-asset term matrices are simplified to age bands.
                max_term(48, 3), max_term(36, 7), max_term(24, 10),
                rule("Class 8 mileage limit", "equipment", "equipment_mileage", "lte", 600000,
                     applies_when=[when("equipment_category", "eq", "class_8_truck")]),
            ],
            "programs": [
                program("Tier 1 - General Program", 1, [
                    min_tib(2), transunion_700,
                    rule("Homeownership", "guarantor", "is_homeowner", "is_true"),
                    rule("App-only limit", "loan", "loan_amount", "lte", 75000),
                ], details={"max_points": 10, "documents": app_only_docs}),
                program("Tier 2 - Start-Up Program", 2, [
                    transunion_700,
                    rule("Homeownership", "guarantor", "is_homeowner", "is_true"),
                    rule("App-only limit", "loan", "loan_amount", "lte", 50000),
                    rule("Class A CDL for 5 years (trucking)", "guarantor", "cdl_years", "gte",
                         5, applies_when=[when("is_trucking", "is_true")]),
                    rule("5 years industry experience", "guarantor",
                         "industry_experience_years", "gte", 5,
                         applies_when=[when("is_trucking", "is_false")]),
                ], applies_when=[when("is_startup", "is_true")],
                    details={"max_points": 7, "documents": app_only_docs, "gps_required": True}),
                program("Tier 2 - Non-Homeowner Program", 3, [
                    min_tib(2), transunion_700,
                    rule("Years at current residence", "guarantor", "years_at_residence", "gte",
                         5),
                    rule("App-only limit", "loan", "loan_amount", "lte", 50000),
                ], applies_when=[when("is_homeowner", "is_false")],
                    details={"max_points": 7, "documents": app_only_docs, "gps_required": True}),
                # The PDF publishes no credit thresholds for Tier 3: it is manual underwriting.
                program("Tier 3 - Full Financials", 4, [],
                        decision_mode="manual_review",
                        description="Transactions $75K-$1MM, or those that do not fit Tier 1/2, "
                                    "considered with a full financial package.",
                        details={"manual_underwriting": True,
                                 "documents": "2 years business + personal tax returns, PFS and "
                                              "debt schedule, articles of incorporation, 3 "
                                              "months bank statements"}),
            ],
        },
    }  # fmt: skip


# ----------------------------------------------------------------------------------------
# Falcon Equipment Finance - "112025 Rates - STANDARD.pdf"
# ----------------------------------------------------------------------------------------


def falcon() -> Json:
    rate_grid = {
        "rates_by_credit_rating": {
            "A": ["9.00%", "8.25%", "7.75%"], "B": ["9.75%", "9.00%", "8.25%"],
            "C": ["10.50%", "10.00%", "9.00%"], "D": ["11.75%", "11.00%", "10.00%"],
            "E": ["13.75%", "13.00%", "12.00%"],
        },
        "bands": ["$15,000 - $50,000", "$50,001 - $150,000", "above $150,000"],
        "adjustments": ["Private party +1.00%", "Titled assets +0.50%",
                        "Aged equipment +0.50% per 15 years"],
        "note": "App-only limit rises by up to $100K (max $350K) with 12+ months clean "
                "payment history.",
    }  # fmt: skip
    comparable = rule("Comparable installment credit (70%)", "credit", "comparable_credit_pct",
                      "gte", 70)  # fmt: skip

    def app_only(limit: int, label: str, applies: list[Json]) -> Json:
        # Exceeding an app-only limit means "send full financials", not a decline -> soft.
        return rule(f"App-only limit ({label})", "loan", "loan_amount", "lte", limit, soft=True,
                    applies_when=applies)  # fmt: skip

    return {
        "lender": {
            "name": "Falcon Equipment Finance",
            "slug": "falcon-equipment-finance",
            "contact_name": "Emma Tickner",
            "contact_email": "ETickner@FalconEquipmentFinance.com",
            "contact_phone": "651.332.6517",
        },
        "policy": {
            "source_document": "112025 Rates - STANDARD.pdf",
            "rules": [
                pg_required(),
                rule("Minimum net financed", "loan", "loan_amount", "gte", 15000,
                     message="Requested amount is {actual}; below {expected} Falcon quotes "
                             "case by case (call for rates)."),
                bankruptcy_seasoning(15),
            ],
            "programs": [
                program("Standard Program", 1, [
                    min_tib(3), min_fico(680), min_paynet(660), comparable,
                    app_only(150000, "logging", [when("industry", "eq", "logging")]),
                    app_only(350000, "manufacturing", [when("industry", "eq", "manufacturing")]),
                    app_only(250000, "commercial",
                             [when("industry", "not_in", ["logging", "manufacturing"])]),
                ], applies_when=[when("is_trucking", "is_false")], details=rate_grid),
                program("Trucking Program (A/B credits only)", 2, [
                    min_tib(5), min_fico(700), min_paynet(680), comparable,
                    rule("Currently operating 5+ trucks", "business", "trucks_operated", "gte",
                         5),
                    rule("Class 8 trucks and trailers 10 years or newer", "equipment",
                         "equipment_age_years", "lte", 10,
                         applies_when=[when("equipment_category", "in",
                                            ["class_8_truck", "trailer"])]),
                    rule("Reefer trailers under 7 years old", "equipment",
                         "equipment_age_years", "lt", 7,
                         applies_when=[when("equipment_category", "eq", "reefer_trailer")]),
                    app_only(150000, "trucking", []),
                ], applies_when=[when("is_trucking", "is_true")], details=rate_grid),
            ],
        },
    }  # fmt: skip


ALL_LENDERS = (stearns, apex, advantage_plus, citizens, falcon)

# Only 4 of the 5 are loaded by `make seed` (see app/seeds/__main__.py). Stearns is deliberately
# left out: the intended first thing to do with the running app is onboard it live from its PDF
# (Lenders -> Onboard from PDF), which exercises the real extraction pipeline instead of trusting
# pre-seeded, hand-modelled data. See DECISIONS.md ("PDF ingestion") for why Stearns specifically.
SEEDED_LENDERS = (apex, advantage_plus, citizens, falcon)
