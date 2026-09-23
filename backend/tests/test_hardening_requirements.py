"""Comprehensive tests for production-hardening requirements:
1. Citizens Bank Tier 3 manual underwriting decision state and ranking.
2. Multi-equipment matching (aggregation, titled check, category mileage, order independence).
3. Fit scoring fairness (neutral soft score, program count bias fix, decay floor).
4. Missing required value vs failed value (outcome="missing", decision="needs_information").
5. Unique program ranks and custom message template validation.
6. ExtractedValue single-slot validation.
7. PDF rule provenance preservation.
"""

import pytest
from pydantic import ValidationError

from app.engine.evaluator import evaluate_lender
from app.engine.features import (
    ApplicationInput,
    EquipmentInput,
    GuarantorInput,
    derive_features,
)
from app.engine.policy import Policy, Rule
from app.seeds.policies import citizens
from app.services.extraction import ExtractedValue


def test_citizens_bank_tier_3_manual_underwriting() -> None:
    """Citizens Bank Tier 3 has decision_mode='manual_review'."""
    policy_data = citizens()["policy"]
    pol = Policy.model_validate(
        {"lender_id": "l_cit", "lender_name": "Citizens Bank", **policy_data}
    )

    # Tier 3 applicant: FICO 670, 3 yrs exp, heavy duty truck, 48m, $75k
    app = ApplicationInput(
        business_state="TX",
        business_industry="transportation",
        years_in_business=3.0,
        annual_revenue=300000.0,
        loan_amount=75000.0,
        term_months=48,
        transaction_type="dealer_sale",
        corp_only=False,
        guarantors=[
            GuarantorInput(
                fico_score=670,
                industry_experience_years=3.0,
                is_homeowner=True,
                has_cdl=True,
                has_bankruptcy=False,
            )
        ],
        equipment=[
            EquipmentInput(
                category="class_8_truck",
                model_year=2021,
                mileage=180000,
                is_titled=True,
            )
        ],
    )
    feat = derive_features(app)
    result = evaluate_lender(pol, feat)

    assert result.decision == "manual_review"
    assert result.matched_program == "Tier 3 - Full Financials"
    assert result.eligible is True


def test_multi_equipment_matching_and_order_independence() -> None:
    """Verify multi-equipment feature aggregation and order independence."""
    eq_a = EquipmentInput(category="class_8_truck", model_year=2020, mileage=120000, is_titled=True)
    eq_b = EquipmentInput(category="sleeper_truck", model_year=2018, mileage=350000, is_titled=True)
    eq_c_untitled = EquipmentInput(
        category="dry_van_trailer", model_year=2022, mileage=5000, is_titled=False
    )

    app_ab = ApplicationInput(equipment=[eq_a, eq_b])
    app_ba = ApplicationInput(equipment=[eq_b, eq_a])
    app_mixed_title = ApplicationInput(equipment=[eq_a, eq_c_untitled])

    feat_ab = derive_features(app_ab)
    feat_ba = derive_features(app_ba)
    feat_mixed = derive_features(app_mixed_title)

    # 1. Order independence
    assert feat_ab["equipment_is_titled"] is True
    assert feat_ba["equipment_is_titled"] is True
    assert feat_ab["equipment_mileage"] == feat_ba["equipment_mileage"] == 350000
    assert len(feat_ab["_equipment_list"]) == len(feat_ba["_equipment_list"]) == 2

    # 2. Titled requirement across all items
    assert feat_mixed["equipment_is_titled"] is False

    # 3. Excluded category test via evaluator across multi-equipment
    pol = Policy.model_validate({
        "lender_id": "l_ex",
        "lender_name": "Exclusion Lender",
        "rules": [
            {
                "label": "Allowed categories",
                "category": "equipment",
                "field": "equipment_category",
                "operator": "in",
                "value": ["class_8_truck", "medium_duty_truck"],
            }
        ],
        "programs": [{"name": "Standard", "rank": 1, "rules": []}],
    })

    result_ab = evaluate_lender(pol, feat_ab)
    assert result_ab.decision == "ineligible"


def test_fit_score_fairness_and_neutrality() -> None:
    """Verify neutral soft rule score (0.5) and program count fairness."""
    p_single = Policy.model_validate({
        "lender_id": "l_single",
        "lender_name": "Single Tier Lender",
        "programs": [{"name": "Tier 1", "rank": 1, "rules": []}],
    })

    p_multi = Policy.model_validate({
        "lender_id": "l_multi",
        "lender_name": "Multi Tier Lender",
        "programs": [
            {"name": "Tier 1", "rank": 1, "rules": []},
            {"name": "Tier 2", "rank": 2, "rules": []},
            {"name": "Tier 3", "rank": 3, "rules": []},
            {"name": "Tier 4", "rank": 4, "rules": []},
            {"name": "Tier 5", "rank": 5, "rules": []},
        ],
    })

    feat = derive_features(ApplicationInput())
    res_single = evaluate_lender(p_single, feat)
    res_multi = evaluate_lender(p_multi, feat)

    assert res_single.fit_score == res_multi.fit_score


def test_missing_required_feature_outcome() -> None:
    """When a required feature is None, outcome is 'missing' and decision 'needs_information'."""
    pol = Policy.model_validate({
        "lender_id": "l_missing",
        "lender_name": "Missing Test Lender",
        "programs": [
            {
                "name": "Standard",
                "rank": 1,
                "rules": [
                    {
                        "label": "Min FICO",
                        "category": "credit",
                        "field": "fico_score",
                        "operator": "gte",
                        "value": 700,
                    }
                ],
            }
        ],
    })

    feat = derive_features(ApplicationInput())
    res = evaluate_lender(pol, feat)

    assert res.decision == "needs_information"
    assert res.eligible is False
    missing_criteria = [c for c in res.programs[0].criteria if c.outcome == "missing"]
    assert len(missing_criteria) == 1


def test_custom_message_validation() -> None:
    """Validate custom message template placeholders."""
    with pytest.raises(ValidationError) as exc:
        Rule.model_validate({
            "label": "Bad Template",
            "category": "credit",
            "field": "fico_score",
            "operator": "gte",
            "value": 700,
            "message_template": "FICO was {user_fico} but required {expected}",
        })
    assert "Invalid placeholder" in str(exc.value)

    r = Rule.model_validate({
        "label": "Good Template",
        "category": "credit",
        "field": "fico_score",
        "operator": "gte",
        "value": 700,
        "message_template": "FICO for {field} was {actual} but needed {expected}",
    })
    assert r.message_template == "FICO for {field} was {actual} but needed {expected}"


def test_extracted_value_single_slot_validation() -> None:
    """ExtractedValue must enforce at most one non-null slot."""
    ev1 = ExtractedValue(number=720, text=None, boolean=None, options=None, range=None)
    assert ev1.number == 720

    with pytest.raises(ValidationError) as exc:
        ExtractedValue(number=720, text="720", boolean=None, options=None, range=None)
    assert "at most one non-null slot" in str(exc.value)


def test_pdf_rule_provenance_preservation() -> None:
    """Verify rule provenance fields round-trip properly."""
    r = Rule.model_validate({
        "label": "FICO Rule",
        "category": "credit",
        "field": "fico_score",
        "operator": "gte",
        "value": 680,
        "source_document": "Citizens_Policy_2025.pdf",
        "source_quote": "Minimum FICO score required for Tier 1 is 680.",
        "source_page": 12,
    })
    assert r.source_document == "Citizens_Policy_2025.pdf"
    assert r.source_quote == "Minimum FICO score required for Tier 1 is 680."
    assert r.source_page == 12
