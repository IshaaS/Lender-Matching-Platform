from datetime import date

import pytest
from pydantic import ValidationError

from app.engine.catalog import CATALOG
from app.engine.evaluator import evaluate_lender, evaluate_rule, rank_results
from app.engine.features import (
    ApplicationInput,
    EquipmentInput,
    GuarantorInput,
    derive_features,
)
from app.engine.operators import OPERATORS
from app.engine.policy import Policy, Rule

TODAY = date(2026, 1, 1)


def rule(**kwargs: object) -> Rule:
    return Rule.model_validate({"label": "Test rule", **kwargs})


def policy(**kwargs: object) -> Policy:
    return Policy.model_validate({"lender_id": "l1", "lender_name": "Test Lender", **kwargs})


def tiered_policy() -> Policy:
    def tier(name: str, rank: int, fico: int) -> dict[str, object]:
        return {
            "name": name,
            "rank": rank,
            "rules": [
                {"label": "Min FICO", "category": "credit", "field": "fico_score",
                 "operator": "gte", "value": fico},
            ],
        }  # fmt: skip

    return policy(
        rules=[
            {"label": "Excluded states", "category": "geography", "field": "business_state",
             "operator": "not_in", "value": ["CA", "NV"]},
        ],
        programs=[tier("Tier 1", 1, 725), tier("Tier 2", 2, 710), tier("Tier 3", 3, 700)],
    )  # fmt: skip


def features(fico: int | None = 720, state: str = "TX", **app: object) -> dict[str, object]:
    return derive_features(
        ApplicationInput(business_state=state, guarantors=[GuarantorInput(fico_score=fico)], **app),
        today=TODAY,
    )


# --- operators -----------------------------------------------------------------------


@pytest.mark.parametrize(
    ("operator", "expected", "actual", "passes"),
    [
        ("gte", 700, 700, True),
        ("gte", 700, 699, False),
        ("gt", 700, 700, False),
        ("gt", 700, 701, True),
        ("lte", 75000, 75000, True),
        ("lte", 75000, 75001, False),
        ("lt", 15, 15, False),
        ("lt", 15, 14, True),
        ("between", [10000, 75000], 10000, True),
        ("between", [10000, 75000], 75000.01, False),
        ("eq", 60, 60, True),
        ("neq", 60, 60, False),
    ],
)
def test_numeric_operators(operator: str, expected: object, actual: float, passes: bool) -> None:
    result = evaluate_rule(
        rule(field="loan_amount", operator=operator, value=expected), {"loan_amount": actual}
    )
    assert (result.outcome == "passed") is passes


@pytest.mark.parametrize(
    ("operator", "value", "actual", "passes"),
    [
        ("in", ["TX", "OK"], "TX", True),
        ("in", ["TX", "OK"], "CA", False),
        ("not_in", ["CA"], "TX", True),
        ("not_in", ["CA"], "CA", False),
    ],
)
def test_list_operators(operator: str, value: list[str], actual: str, passes: bool) -> None:
    result = evaluate_rule(
        rule(field="business_state", operator=operator, value=value), {"business_state": actual}
    )
    assert (result.outcome == "passed") is passes


@pytest.mark.parametrize(
    ("operator", "actual", "passes"),
    [("is_true", True, True), ("is_true", False, False), ("is_false", False, True),
     ("is_false", True, False)],
)  # fmt: skip
def test_boolean_operators(operator: str, actual: bool, passes: bool) -> None:
    result = evaluate_rule(rule(field="is_homeowner", operator=operator), {"is_homeowner": actual})
    assert (result.outcome == "passed") is passes


def test_every_operator_is_exercised_above() -> None:
    assert set(OPERATORS) == {
        "gte", "gt", "lte", "lt", "between", "eq", "neq", "in", "not_in", "is_true", "is_false",
    }  # fmt: skip


# --- rule validation -------------------------------------------------------------------


@pytest.mark.parametrize(
    "bad",
    [
        {"field": "no_such_field", "operator": "gte", "value": 1},
        {"field": "fico_score", "operator": "no_such_op", "value": 1},
        {"field": "fico_score", "operator": "gte", "value": "seven hundred"},
        {"field": "fico_score", "operator": "in", "value": [700]},  # list op on a number
        {"field": "business_state", "operator": "not_in", "value": ["ZZ"]},
        {"field": "business_state", "operator": "not_in", "value": []},
        {"field": "loan_amount", "operator": "between", "value": [75000, 10000]},
        {"field": "is_homeowner", "operator": "gte", "value": 1},
        {"kind": "any_of", "alternatives": []},
    ],
)
def test_invalid_rules_are_rejected(bad: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        rule(**bad)


# --- messages, missing data, conditions ---------------------------------------------------


def test_failure_message_states_expected_and_actual() -> None:
    result = evaluate_rule(
        rule(label="Min FICO", field="fico_score", operator="gte", value=700), {"fico_score": 600}
    )
    assert result.outcome == "failed"
    assert result.message == "FICO score is 600, below the minimum of 700."
    assert (result.expected, result.actual) == (700, 600)


def test_money_and_percent_are_formatted() -> None:
    amount = evaluate_rule(
        rule(field="loan_amount", operator="lte", value=75000), {"loan_amount": 120000}
    )
    assert amount.message == "Requested amount is $120,000, above the maximum of $75,000."
    pct = evaluate_rule(
        rule(field="comparable_credit_pct", operator="gte", value=70),
        {"comparable_credit_pct": 42.5},
    )
    assert "42.5%" in pct.message and "70%" in pct.message


def test_custom_message_template() -> None:
    result = evaluate_rule(
        rule(field="business_state", operator="not_in", value=["CA"],
             message_template="Lender does not operate in {actual}."),
        {"business_state": "CA"},
    )  # fmt: skip
    assert result.message == "Lender does not operate in CA."


def test_missing_value_fails_with_not_provided() -> None:
    result = evaluate_rule(
        rule(field="paynet_score", operator="gte", value=660), {"paynet_score": None}
    )
    assert result.outcome == "missing"
    assert "was not provided" in result.message


def test_applies_when_skips_rule() -> None:
    bankruptcy = rule(
        label="Bankruptcy seasoning",
        field="years_since_bankruptcy_discharge",
        operator="gte",
        value=7,
        applies_when=[{"field": "has_bankruptcy", "operator": "is_true"}],
    )
    clean = evaluate_rule(bankruptcy, {"has_bankruptcy": False})
    assert clean.outcome == "skipped"
    assert clean.message == "Not applicable: only checked when Bankruptcy on record is yes."
    recent = evaluate_rule(
        bankruptcy, {"has_bankruptcy": True, "years_since_bankruptcy_discharge": 4.0}
    )
    assert recent.outcome == "failed"
    seasoned = evaluate_rule(
        bankruptcy, {"has_bankruptcy": True, "years_since_bankruptcy_discharge": 9.0}
    )
    assert seasoned.outcome == "passed"


def test_any_of_rule() -> None:
    comparable = rule(
        kind="any_of",
        label="Comparable debt",
        alternatives=[
            {"field": "comparable_credit_pct", "operator": "gte", "value": 100,
             "label": "a single account at least the size of the request"},
            {"field": "comparable_contracts_count", "operator": "gte", "value": 3,
             "label": "3+ contracts with recent payment activity"},
        ],
    )  # fmt: skip
    via_second = evaluate_rule(
        comparable, {"comparable_credit_pct": 40, "comparable_contracts_count": 4}
    )
    assert via_second.outcome == "passed"
    assert "3+ contracts" in via_second.message
    neither = evaluate_rule(
        comparable, {"comparable_credit_pct": 40, "comparable_contracts_count": 1}
    )
    assert neither.outcome == "failed"
    assert "needs one of" in neither.message


# --- lender evaluation -----------------------------------------------------------------


def test_best_tier_is_matched() -> None:
    result = evaluate_lender(tiered_policy(), features(fico=760))
    assert result.eligible and result.matched_program == "Tier 1"
    assert result.rejection_reasons == []


def test_falls_to_lower_tier() -> None:
    result = evaluate_lender(tiered_policy(), features(fico=712))
    assert result.eligible and result.matched_program == "Tier 2"


def test_ineligible_reports_lowest_bar() -> None:
    result = evaluate_lender(tiered_policy(), features(fico=600))
    assert not result.eligible and result.fit_score == 0
    assert result.rejection_reasons == ["Tier 3: FICO score is 600, below the minimum of 700."]
    assert result.near_miss_ratio == 0.5  # state passed, FICO failed


def test_restriction_overrides_programs() -> None:
    result = evaluate_lender(tiered_policy(), features(fico=800, state="CA"))
    assert not result.eligible and result.matched_program is None
    assert result.rejection_reasons == [
        "Business state is CA, which is on this lender's exclusion list."
    ]
    # Programs are still evaluated so the UI can show that credit was otherwise fine.
    assert result.programs[0].eligible


def test_program_applicability() -> None:
    pol = policy(
        programs=[
            {"name": "Standard", "rank": 1,
             "applies_when": [{"field": "has_paynet", "operator": "is_true"}],
             "rules": [{"label": "PayNet", "field": "paynet_score", "operator": "gte",
                        "value": 685}]},
            {"name": "No PayNet", "rank": 2,
             "applies_when": [{"field": "has_paynet", "operator": "is_false"}],
             "rules": [{"label": "FICO", "field": "fico_score", "operator": "gte",
                        "value": 735}]},
        ]
    )  # fmt: skip
    result = evaluate_lender(pol, features(fico=740))
    assert result.matched_program == "No PayNet"
    standard = result.programs[0]
    assert not standard.applicable and standard.criteria == []
    assert "PayNet score available" in (standard.applicability_note or "")


def test_no_applicable_program() -> None:
    pol = policy(
        programs=[{"name": "Medical", "rank": 1,
                   "applies_when": [{"field": "is_medical", "operator": "is_true"}]}]
    )  # fmt: skip
    result = evaluate_lender(pol, features(industry="construction"))
    assert not result.eligible
    assert result.rejection_reasons[0] == "No program applies to this application."


def test_soft_rule_never_rejects_but_lowers_score() -> None:
    def with_soft(threshold: int) -> Policy:
        return policy(
            programs=[{"name": "Only", "rank": 1, "rules": [
                {"label": "Min FICO", "field": "fico_score", "operator": "gte", "value": 680},
                {"label": "Prefers long trade history", "severity": "soft",
                 "field": "trade_history_years", "operator": "gte", "value": threshold},
            ]}]
        )  # fmt: skip

    f = features(fico=720, trade_history_years=4)
    met, unmet = evaluate_lender(with_soft(3), f), evaluate_lender(with_soft(7), f)
    assert met.eligible and unmet.eligible
    assert unmet.fit_score == met.fit_score - 20


# --- scoring ---------------------------------------------------------------------------


def test_score_bounds_and_monotonicity() -> None:
    pol = tiered_policy()
    scores = [evaluate_lender(pol, features(fico=f)).fit_score for f in (700, 705, 712, 730, 850)]
    assert all(0 <= s <= 100 for s in scores)
    assert scores == sorted(scores)
    assert scores[-1] == 90  # top tier, max headroom, no unmet preferences (neutral soft score 0.5)


def test_better_tier_outscores_lower_tier() -> None:
    pol = tiered_policy()
    assert (
        evaluate_lender(pol, features(fico=725)).fit_score
        > evaluate_lender(pol, features(fico=724)).fit_score
    )


def test_ranking_orders_eligible_by_score_then_near_miss() -> None:
    pol = tiered_policy()
    strong = evaluate_lender(pol, features(fico=800))
    weak = evaluate_lender(pol, features(fico=701))
    rejected = evaluate_lender(pol, features(fico=600))
    blocked = evaluate_lender(pol, features(fico=600, state="CA"))
    ranked = rank_results([rejected, blocked, weak, strong])
    assert ranked == [strong, weak, rejected, blocked]


# --- feature derivation ------------------------------------------------------------------


def test_features_cover_the_whole_catalog() -> None:
    non_private_features = set(
        k for k in derive_features(ApplicationInput(), today=TODAY) if not k.startswith("_")
    )
    assert non_private_features == set(CATALOG)


def test_derived_features() -> None:
    f = derive_features(
        ApplicationInput(
            industry="trucking",
            years_in_business=1.5,
            loan_amount=100_000,
            largest_comparable_credit=70_000,
            paynet_score=None,
            guarantors=[
                GuarantorInput(ownership_pct=60, fico_score=740, revolving_credit_limit=40_000,
                               revolving_balance=10_000, unsecured_debt=5_000,
                               is_us_citizen=True),
                GuarantorInput(ownership_pct=40, fico_score=690, has_bankruptcy=True,
                               bankruptcy_discharge_date=date(2018, 1, 1), is_us_citizen=True),
                GuarantorInput(ownership_pct=5, fico_score=500),  # below PG threshold: ignored
            ],
            equipment=[EquipmentInput(category="class_8_truck", model_year=2019, mileage=410_000),
                       EquipmentInput(category="trailer", model_year=2015)],
        ),
        today=TODAY,
    )  # fmt: skip
    assert f["is_startup"] is True and f["is_trucking"] is True and f["is_medical"] is False
    assert f["has_paynet"] is False
    assert f["fico_score"] == 690  # weakest qualifying guarantor
    assert f["comparable_credit_pct"] == 70.0
    assert f["revolving_available_pct"] == 75.0
    assert f["revolving_plus_unsecured_debt"] == 15_000
    assert f["has_bankruptcy"] is True and f["years_since_bankruptcy_discharge"] == 8.0
    assert f["equipment_age_years"] == 11  # oldest item
    assert f["equipment_category"] == "class_8_truck"
    assert f["is_us_citizen"] is True


def test_undischarged_bankruptcy_counts_as_zero_years() -> None:
    f = derive_features(
        ApplicationInput(guarantors=[GuarantorInput(has_bankruptcy=True)]), today=TODAY
    )
    assert f["years_since_bankruptcy_discharge"] == 0.0


def test_engine_has_no_infrastructure_imports() -> None:
    import ast
    import pathlib

    import app.engine as engine

    banned = ("app.api", "app.models", "app.db", "app.workflows", "sqlalchemy", "fastapi")
    for path in pathlib.Path(engine.__file__).parent.glob("*.py"):
        for node in ast.walk(ast.parse(path.read_text())):
            if isinstance(node, ast.Import):
                modules = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                modules = [node.module or ""]
            else:
                continue
            for module in modules:
                assert not module.startswith(banned), f"{path.name} imports {module}"
