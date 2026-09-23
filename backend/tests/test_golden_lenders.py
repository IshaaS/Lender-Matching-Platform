"""Golden cases: each expectation below is traceable to a line in a lender PDF."""

import copy
from datetime import date
from typing import Any

import pytest

from app.engine.adapters import application_input_from_payload
from app.engine.evaluator import LenderEvaluation, evaluate_lender, rank_results
from app.engine.features import derive_features
from app.engine.policy import Policy
from app.seeds import policies, samples

TODAY = date(2026, 1, 1)


def load(factory: Any) -> Policy:
    seed = factory()
    return Policy.model_validate(
        {"lender_id": seed["lender"]["slug"], "lender_name": seed["lender"]["name"],
         **seed["policy"]}
    )  # fmt: skip


POLICIES = {fn.__name__: load(fn) for fn in policies.ALL_LENDERS}


def run(lender: str, sample: dict[str, Any], **changes: Any) -> LenderEvaluation:
    """Evaluate a sample with dotted-path overrides, e.g. **{"guarantors.0.fico_score": 600}."""
    payload = copy.deepcopy(sample)
    for path, value in changes.items():
        *parents, leaf = path.split(".")
        node: Any = payload
        for part in parents:
            node = node[int(part)] if part.isdigit() else node[part]
        node[leaf] = value
    features = derive_features(application_input_from_payload(payload), today=TODAY)
    return evaluate_lender(POLICIES[lender], features)


def reasons(result: LenderEvaluation) -> str:
    return " | ".join(result.rejection_reasons)


def test_all_seed_policies_validate() -> None:
    assert len(POLICIES) == 5
    assert sum(len(p.programs) for p in POLICIES.values()) == 24


# --- the four demo applications, across all lenders ---------------------------------------

EXPECTED = {
    "strong": {"stearns": "Tier 1", "apex": "A+ Rate", "advantage_plus": None,
               "citizens": "Tier 3 - Full Financials", "falcon": "Standard Program"},
    "marginal": {"stearns": None, "apex": "C Rate", "advantage_plus": "Established Business",
                 "citizens": "Tier 3 - Full Financials", "falcon": None},
    "trucking": {"stearns": None, "apex": None, "advantage_plus": None,
                 "citizens": "Tier 3 - Full Financials",
                 "falcon": "Trucking Program (A/B credits only)"},
    "startup": {"stearns": None, "apex": "Medical A Rate", "advantage_plus": "Start-Up",
                "citizens": "Tier 2 - Start-Up Program", "falcon": None},
}  # fmt: skip


@pytest.mark.parametrize("sample", samples.SAMPLES, ids=lambda s: s["key"])
@pytest.mark.parametrize("lender", list(POLICIES))
def test_sample_matrix(lender: str, sample: dict[str, Any]) -> None:
    result = run(lender, sample)
    assert result.matched_program == EXPECTED[sample["key"]][lender], reasons(result)
    assert result.eligible is (result.matched_program is not None)
    assert bool(result.rejection_reasons) is not result.eligible


def test_strong_sample_ranking() -> None:
    ranked = rank_results([run(lender, samples.STRONG) for lender in POLICIES])
    assert [r.eligible for r in ranked] == [True, True, True, True, False]
    assert ranked[-1].lender_name == "Advantage+ Financing"
    # A manual-underwriting fallback tier must not outrank real credit-box matches.
    assert ranked[3].lender_name == "Citizens Bank"


# --- Stearns ------------------------------------------------------------------------------


def test_stearns_tiers_step_down_with_fico() -> None:
    assert run("stearns", samples.STRONG).matched_program == "Tier 1"
    assert run("stearns", samples.STRONG, **{"guarantors.0.fico_score": 712}).matched_program == (
        "Tier 2"
    )
    assert run("stearns", samples.STRONG, **{"guarantors.0.fico_score": 701}).matched_program == (
        "Tier 3"
    )


def test_stearns_no_paynet_uses_alternative_table() -> None:
    no_score = {"business_credit.paynet_score": None}
    assert run("stearns", samples.STRONG, **no_score).matched_program == "Tier 1 (No PayNet)"
    # 725 clears standard Tier 1 but the no-PayNet table demands 735 for Tier 1.
    result = run("stearns", samples.STRONG, **no_score, **{"guarantors.0.fico_score": 725})
    assert result.matched_program == "Tier 2 (No PayNet)"


def test_stearns_corp_only_needs_ten_years_for_tier_1() -> None:
    result = run("stearns", samples.STRONG, **{"loan.corp_only": True})
    assert result.matched_program == "Tier 2 (Corp Only)"  # 8 years TIB, PayNet 700


def test_stearns_recent_bankruptcy_and_restricted_industry() -> None:
    bk = run("stearns", samples.STRONG, **{"guarantors.0.has_bankruptcy": True,
             "guarantors.0.bankruptcy_discharge_date": "2021-06-01"})  # fmt: skip
    assert not bk.eligible and "bankruptcy" in reasons(bk).lower()
    restaurant = run("stearns", samples.STRONG, **{"business.industry": "restaurant"})
    assert not restaurant.eligible and "exclusion list" in reasons(restaurant)


def test_stearns_comparable_debt_alternatives() -> None:
    weak = {"business_credit.largest_comparable_credit": 40000}
    assert run("stearns", samples.STRONG, **weak).eligible  # still has 4 contracts
    neither = run("stearns", samples.STRONG, **weak,
                  **{"business_credit.comparable_contracts_count": 1})  # fmt: skip
    assert not neither.eligible and "Comparable debt" in reasons(neither)


# --- Apex -----------------------------------------------------------------------------------


def test_apex_program_ladder() -> None:
    assert run("apex", samples.STRONG).matched_program == "A+ Rate"
    # Collateral older than 5 years loses A+ but keeps A.
    assert run("apex", samples.STRONG, **{"equipment.0.model_year": 2018}).matched_program == (
        "A Rate"
    )
    b = run("apex", samples.STRONG, **{"guarantors.0.fico_score": 675,
            "business.years_in_business": 3, "business_credit.paynet_score": 652})  # fmt: skip
    assert b.matched_program == "B Rate"


def test_apex_excluded_state_and_old_equipment() -> None:
    ca = run("apex", samples.STRONG, **{"business.state": "CA"})
    assert not ca.eligible and "Apex does not lend in CA" in reasons(ca)
    old = run("apex", samples.STRONG, **{"equipment.0.model_year": 2005})
    assert not old.eligible and "Equipment age is 21 years" in reasons(old)


def test_apex_comparable_borrowing_depends_on_amount() -> None:
    thin = {"business_credit.largest_comparable_credit": 30000}
    assert run("apex", samples.STRONG, **thin, **{"loan.amount": 45000}).eligible  # no rule
    assert run("apex", samples.STRONG, **thin, **{"loan.amount": 60000}).eligible  # 50% rule
    over = run("apex", samples.STRONG, **thin, **{"loan.amount": 120000})  # 75% rule: 25%
    assert not over.eligible and "75%" in reasons(over)


def test_apex_c_rate_is_capped_at_100k() -> None:
    result = run("apex", samples.MARGINAL, **{"loan.amount": 101000,
                 "business_credit.largest_comparable_credit": 101000})  # fmt: skip
    assert not result.eligible
    assert "C Rate: Requested amount is $101,000, above the maximum of $100,000." in reasons(result)


# --- Advantage+ -----------------------------------------------------------------------------


def test_advantage_plus_amount_window_and_derogatories() -> None:
    assert "$120,000" in reasons(run("advantage_plus", samples.STRONG))
    ok = run("advantage_plus", samples.STRONG, **{"loan.amount": 75000})
    assert ok.matched_program == "Established Business"
    lien = run("advantage_plus", samples.STRONG, **{"loan.amount": 75000,
               "guarantors.0.has_tax_liens": True})  # fmt: skip
    assert not lien.eligible and "Tax liens" in reasons(lien)


def test_advantage_plus_startups_need_700() -> None:
    assert run("advantage_plus", samples.STARTUP).matched_program == "Start-Up"
    low = run("advantage_plus", samples.STARTUP, **{"guarantors.0.fico_score": 690})
    assert not low.eligible  # 690 would pass the established program, but not start-up
    assert "Start-Up: FICO score is 690, below the minimum of 700." in reasons(low)


def test_advantage_plus_preferences_only_affect_score() -> None:
    base = {"loan.amount": 75000}
    preferred = run("advantage_plus", samples.STRONG, **base,
                    **{"business_credit.largest_comparable_credit": 75000})  # fmt: skip
    thin = run("advantage_plus", samples.STRONG, **base,
               **{"business_credit.trade_history_years": 2,
                  "business_credit.largest_comparable_credit": 20000})  # fmt: skip
    assert preferred.eligible and thin.eligible
    assert preferred.fit_score > thin.fit_score


# --- Citizens -------------------------------------------------------------------------------


def test_citizens_tiers() -> None:
    assert run("citizens", samples.STRONG, **{"loan.amount": 70000}).matched_program == (
        "Tier 1 - General Program"
    )
    renter = run("citizens", samples.STRONG, **{"loan.amount": 45000,
                 "guarantors.0.is_homeowner": False})  # fmt: skip
    assert renter.matched_program == "Tier 2 - Non-Homeowner Program"
    assert run("citizens", samples.STRONG).matched_program == "Tier 3 - Full Financials"


def test_citizens_hard_stops() -> None:
    ca = run("citizens", samples.STRONG, **{"business.state": "CA"})
    assert not ca.eligible and "no longer finances applicants in CA" in reasons(ca)
    refi = run("citizens", samples.STRONG, **{"loan.transaction_type": "refinance"})
    assert not refi.eligible
    bk = run("citizens", samples.STRONG, **{"guarantors.0.has_bankruptcy": True,
             "guarantors.0.bankruptcy_discharge_date": "2019-01-01"})  # fmt: skip
    assert bk.eligible  # 7 years since discharge clears Citizens' 5-year rule


def test_citizens_cdl_or_fleet_and_term_by_age() -> None:
    no_cdl = run("citizens", samples.TRUCKING, **{"guarantors.0.has_cdl": False})
    assert not no_cdl.eligible and "CDL" in reasons(no_cdl)
    fleet = run("citizens", samples.TRUCKING, **{"guarantors.0.has_cdl": False,
                "business.trucks_operated": 12})  # fmt: skip
    assert fleet.eligible
    long_term = run("citizens", samples.TRUCKING, **{"loan.term_months": 60})
    assert not long_term.eligible  # 5-year-old truck is limited to 48 months
    assert "above the maximum of 48 months" in reasons(long_term)


# --- Falcon ---------------------------------------------------------------------------------


def test_falcon_standard_box() -> None:
    assert run("falcon", samples.STRONG).matched_program == "Standard Program"
    low = run("falcon", samples.STRONG, **{"business_credit.paynet_score": 650})
    assert not low.eligible
    assert "PayNet MasterScore is 650, below the minimum of 660." in reasons(low)
    small = run("falcon", samples.STRONG, **{"loan.amount": 12000})
    assert not small.eligible and "call for rates" in reasons(small)


def test_falcon_trucking_overlay() -> None:
    assert run("falcon", samples.TRUCKING).eligible
    small_fleet = run("falcon", samples.TRUCKING, **{"business.trucks_operated": 3})
    assert not small_fleet.eligible and "Trucks operated is 3" in reasons(small_fleet)
    old_truck = run("falcon", samples.TRUCKING, **{"equipment.0.model_year": 2014})
    assert not old_truck.eligible and "Equipment age is 12 years" in reasons(old_truck)
    # The same 690 PayNet / 715 FICO would pass the standard box but trucking demands more TIB.
    young = run("falcon", samples.TRUCKING, **{"business.years_in_business": 4})
    assert not young.eligible


def test_falcon_app_only_limit_is_soft() -> None:
    big = run("falcon", samples.STRONG, **{"loan.amount": 300000,
              "business_credit.largest_comparable_credit": 300000})  # fmt: skip
    assert big.eligible
    assert big.fit_score < run("falcon", samples.STRONG).fit_score
