"""The matching engine: (features, policy) -> explained eligibility decision.

Pure functions only. No database, web framework or workflow imports belong here.
"""

from typing import Any, Literal

from pydantic import BaseModel, Field

from app.engine.catalog import get_field
from app.engine.features import FeatureSet
from app.engine.formatting import build_message, format_expected, format_value
from app.engine.operators import get_operator
from app.engine.policy import Condition, Policy, Program, Rule
from app.engine.scoring import ScoreBreakdown, score_match

Outcome = Literal["passed", "failed", "skipped", "missing"]
DecisionState = Literal["eligible", "manual_review", "needs_information", "ineligible", "error"]


class CriterionOutcome(BaseModel):
    rule_id: str | None = None
    label: str
    category: str
    severity: str
    outcome: Outcome
    field: str | None = None
    operator: str | None = None
    expected: Any = None
    actual: Any = None
    message: str


class ProgramEvaluation(BaseModel):
    program_id: str | None = None
    name: str
    rank: int
    decision_mode: str = "automatic"
    applicable: bool
    applicability_note: str | None = None
    eligible: bool = False
    decision: DecisionState = "ineligible"
    hard_failures: int = 0
    missing_fields_count: int = 0
    criteria: list[CriterionOutcome] = Field(default_factory=list)
    details: dict[str, Any] = Field(default_factory=dict)


class LenderEvaluation(BaseModel):
    lender_id: str
    lender_name: str
    version_id: str | None = None
    version_number: int = 1
    eligible: bool = False
    decision: DecisionState = "ineligible"
    matched_program: str | None = None
    fit_score: int = 0
    score_breakdown: ScoreBreakdown | None = None
    near_miss_ratio: float = 0.0
    rejection_reasons: list[str] = Field(default_factory=list)
    restrictions: list[CriterionOutcome] = Field(default_factory=list)
    programs: list[ProgramEvaluation] = Field(default_factory=list)


def _test_equipment(
    items: list[dict[str, Any]], field: str, operator: str, expected: Any, rule: Rule | None = None
) -> tuple[bool | None, Any]:
    if not items:
        return None, None

    # Filter items if rule applies conditionally to a specific category
    relevant_items = items
    if rule and rule.applies_when:
        for c in rule.applies_when:
            if c.field == "equipment_category" and c.operator == "eq":
                relevant_items = [i for i in items if i.get("category") == c.value]
                break

    if not relevant_items:
        # No equipment items match the condition; rule does not apply to this application
        return True, [i.get("category") for i in items]

    if field == "equipment_category":
        categories = [i.get("category") for i in relevant_items]
        if any(c is None for c in categories):
            return None, None
        op = get_operator(operator)
        if operator == "not_in":
            # Excluded categories: fail if ANY asset belongs to an excluded category
            for cat in categories:
                if not op.test(cat, expected):
                    return False, cat
            return True, categories
        elif operator == "in":
            # Allowed categories: ALL assets must belong to allowed categories
            for cat in categories:
                if not op.test(cat, expected):
                    return False, cat
            return True, categories
        elif operator in ("eq", "neq"):
            for cat in categories:
                if not op.test(cat, expected):
                    return False, cat
            return True, categories

    elif field == "equipment_is_titled":
        titled_states = [i.get("is_titled") for i in relevant_items]
        if any(t is None for t in titled_states):
            return None, None
        if operator in ("is_true", "eq"):
            if not all(t is True for t in titled_states):
                return False, False
            return True, True

    elif field == "equipment_age_years":
        raw_ages = [i.get("age_years") for i in relevant_items]
        if any(a is None for a in raw_ages):
            return None, None
        ages = [a for a in raw_ages if a is not None]
        op = get_operator(operator)
        for age in ages:
            if not op.test(age, expected):
                return False, max(ages)
        return True, max(ages)

    elif field == "equipment_mileage":
        raw_mileages = [i.get("mileage") for i in relevant_items]
        if any(m is None for m in raw_mileages):
            return None, None
        mileages = [m for m in raw_mileages if m is not None]
        op = get_operator(operator)
        for m in mileages:
            if not op.test(m, expected):
                return False, max(mileages)
        return True, max(mileages)

    # Default fallback for single primary equipment item
    primary = relevant_items[0]
    key_map = {
        "equipment_category": "category",
        "equipment_age_years": "age_years",
        "equipment_mileage": "mileage",
        "equipment_condition": "condition",
        "equipment_is_titled": "is_titled",
    }
    item_key = key_map.get(field)
    actual = primary.get(item_key) if item_key else None
    if actual is None:
        return None, None
    return bool(get_operator(operator).test(actual, expected)), actual


def _test(
    features: FeatureSet, field: str, operator: str, expected: Any, rule: Rule | None = None
) -> tuple[bool | None, Any]:
    items = features.get("_equipment_list")
    if field.startswith("equipment_") and isinstance(items, list) and len(items) > 0:
        return _test_equipment(items, field, operator, expected, rule)

    actual = features.get(field)
    if actual is None:
        return None, None
    return bool(get_operator(operator).test(actual, expected)), actual


def _condition_holds(features: FeatureSet, condition: Condition) -> bool:
    res, _ = _test(features, condition.field, condition.operator, condition.value)
    return res is True


def _describe(condition: Condition) -> str:
    fdef, op = get_field(condition.field), get_operator(condition.operator)
    expected = format_expected(fdef, op, condition.value)
    return f"{fdef.label} {op.label} {expected}".strip()


def evaluate_rule(rule: Rule, features: FeatureSet) -> CriterionOutcome:
    base = {
        "rule_id": rule.id,
        "label": rule.label,
        "category": rule.category,
        "severity": rule.severity,
    }

    unmet = [c for c in rule.applies_when if not _condition_holds(features, c)]
    if unmet:
        return CriterionOutcome(
            **base,
            outcome="skipped",
            field=rule.field,
            operator=rule.operator,
            expected=rule.value,
            message=f"Not applicable: only checked when {_describe(unmet[0])}.",
        )

    if rule.kind == "any_of":
        attempts = [(c, *_test(features, c.field, c.operator, c.value)) for c in rule.alternatives]
        satisfied = next((c for c, ok, _ in attempts if ok is True), None)
        has_missing = any(ok is None for _, ok, _ in attempts)
        if satisfied:
            message = f"{rule.label}: satisfied by {satisfied.label or _describe(satisfied)}."
            outcome = "passed"
        elif has_missing and not any(ok is False for _, ok, _ in attempts):
            message = f"{rule.label}: required information not provided."
            outcome = "missing"
        else:
            seen = "; ".join(
                f"{get_field(c.field).label} is {format_value(get_field(c.field), actual)}"
                for c, _, actual in attempts
            )
            options = " OR ".join(c.label or _describe(c) for c in rule.alternatives)
            message = rule.message_template or f"{rule.label}: needs one of [{options}]. {seen}."
            outcome = "failed"
        return CriterionOutcome(
            **base,
            outcome=outcome,
            expected=[c.model_dump() for c in rule.alternatives],
            actual={c.field: actual for c, _, actual in attempts},
            message=message,
        )

    assert rule.field and rule.operator  # guaranteed by Rule validation
    passed_state, actual = _test(features, rule.field, rule.operator, rule.value, rule)
    if passed_state is None:
        outcome = "missing"
        fdef = get_field(rule.field)
        message = (
            rule.message_template
            or f"{fdef.label} was not provided; this value is required to determine eligibility."
        )
    elif passed_state is True:
        outcome = "passed"
        message = build_message(
            get_field(rule.field),
            get_operator(rule.operator),
            rule.value,
            actual,
            True,
            rule.message_template,
        )
    else:
        outcome = "failed"
        message = build_message(
            get_field(rule.field),
            get_operator(rule.operator),
            rule.value,
            actual,
            False,
            rule.message_template,
        )

    return CriterionOutcome(
        **base,
        outcome=outcome,
        field=rule.field,
        operator=rule.operator,
        expected=rule.value,
        actual=actual,
        message=message,
    )


def _hard_failures(criteria: list[CriterionOutcome]) -> list[CriterionOutcome]:
    return [c for c in criteria if c.severity == "hard" and c.outcome == "failed"]


def _evaluate_program(program: Program, features: FeatureSet) -> ProgramEvaluation:
    unmet = [c for c in program.applies_when if not _condition_holds(features, c)]
    if unmet:
        return ProgramEvaluation(
            program_id=program.id,
            name=program.name,
            rank=program.rank,
            decision_mode=program.decision_mode,
            applicable=False,
            applicability_note=f"Program only applies when {_describe(unmet[0])}.",
            details=program.details,
        )
    criteria = [evaluate_rule(rule, features) for rule in program.rules]
    failures = len([c for c in criteria if c.severity == "hard" and c.outcome == "failed"])
    missing_count = len([c for c in criteria if c.severity == "hard" and c.outcome == "missing"])

    if failures > 0:
        decision = "ineligible"
        eligible = False
    elif missing_count > 0:
        decision = "needs_information"
        eligible = False
    elif program.decision_mode == "manual_review":
        decision = "manual_review"
        eligible = True
    else:
        decision = "eligible"
        eligible = True

    return ProgramEvaluation(
        program_id=program.id,
        name=program.name,
        rank=program.rank,
        decision_mode=program.decision_mode,
        applicable=True,
        eligible=eligible,
        decision=decision,
        hard_failures=failures,
        missing_fields_count=missing_count,
        criteria=criteria,
        details=program.details,
    )


def evaluate_lender(policy: Policy, features: FeatureSet) -> LenderEvaluation:
    restrictions = [evaluate_rule(rule, features) for rule in policy.rules]
    restriction_failures = [
        c for c in restrictions if c.severity == "hard" and c.outcome == "failed"
    ]
    restriction_missing = [
        c for c in restrictions if c.severity == "hard" and c.outcome == "missing"
    ]

    programs = [
        _evaluate_program(p, features) for p in sorted(policy.programs, key=lambda p: p.rank)
    ]
    applicable = [p for p in programs if p.applicable]

    # Program selection priority:
    # 1. First applicable program with decision == "eligible"
    # 2. First applicable program with decision == "manual_review"
    # 3. First applicable program with decision == "needs_information"
    matched = None
    if not restriction_failures:
        matched = (
            next((p for p in applicable if p.decision == "eligible"), None)
            or next((p for p in applicable if p.decision == "manual_review"), None)
            or next((p for p in applicable if p.decision == "needs_information"), None)
        )

    # Determine overall lender decision:
    if restriction_failures:
        decision = "ineligible"
        eligible = False
    elif matched is not None:
        decision = matched.decision
        eligible = (decision in ("eligible", "manual_review"))
    elif restriction_missing:
        decision = "needs_information"
        eligible = False
    else:
        decision = "ineligible"
        eligible = False

    # Program closest for rejection reasons
    closest = matched or min(
        applicable, key=lambda p: (p.hard_failures, p.missing_fields_count, -p.rank), default=None
    )

    reasons = [c.message for c in restriction_failures]
    if not applicable:
        reasons.append("No program applies to this application.")
        reasons.extend(p.applicability_note for p in programs if p.applicability_note)
    elif matched is None and closest is not None:
        reasons.extend(f"{closest.name}: {c.message}" for c in _hard_failures(closest.criteria))

    considered = restrictions + (closest.criteria if closest else [])
    hard = [c for c in considered if c.severity == "hard" and c.outcome != "skipped"]
    near_miss = round(sum(c.outcome == "passed" for c in hard) / len(hard), 3) if hard else 0.0

    result = LenderEvaluation(
        lender_id=policy.lender_id,
        lender_name=policy.lender_name,
        version_id=policy.version_id,
        version_number=policy.version_number,
        eligible=eligible,
        decision=decision,
        matched_program=matched.name if matched else None,
        near_miss_ratio=near_miss,
        rejection_reasons=reasons,
        restrictions=restrictions,
        programs=programs,
    )

    if matched and matched.decision in ("eligible", "manual_review"):
        breakdown = score_match(
            position=applicable.index(matched),
            program_count=len(applicable),
            criteria=restrictions + matched.criteria,
        )
        result.score_breakdown = breakdown
        result.fit_score = breakdown.total

    return result


DECISION_RANK = {
    "eligible": 1,
    "manual_review": 2,
    "needs_information": 3,
    "ineligible": 4,
    "error": 5,
}


def rank_results(results: list[LenderEvaluation]) -> list[LenderEvaluation]:
    """Eligible lenders by fit score, then manual review, then needs info, then ineligible."""
    return sorted(
        results,
        key=lambda r: (
            DECISION_RANK.get(r.decision, 4),
            -r.fit_score,
            -r.near_miss_ratio,
            r.lender_name,
        ),
    )
