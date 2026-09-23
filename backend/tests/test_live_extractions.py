"""Regression suite for the extractor: recorded live responses vs. the hand-modelled seeds.

tests/fixtures/extractions-live/<provider>/ holds real model responses for the five provided
PDFs (recorded 2026-09-22 with gpt-5.5 via Azure OpenAI). Re-recording them after a prompt or
schema change and re-running this file shows whether extraction got better or worse, without
spending tokens in CI.

Two levels of agreement are asserted:
- eligibility on every sample application must match the seed for every lender (hard bar)
- the matched tier's position must match where the extractor chose the same program structure;
  known, documented structural differences are listed in STRUCTURAL_DIFFERENCES
"""

from datetime import date
from pathlib import Path
from typing import Any

import pytest

from app.engine.adapters import application_input_from_payload
from app.engine.evaluator import LenderEvaluation, evaluate_lender
from app.engine.features import derive_features
from app.engine.policy import Policy
from app.seeds import policies as seeds
from app.seeds import samples
from app.services.extraction import ExtractedPolicy, ExtractedValue, _coerce, build_draft

LIVE = Path(__file__).parent / "fixtures" / "extractions-live"
SEEDS = {
    "EF Credit Box 4.14.2025": seeds.stearns,
    "Apex EF Broker Guidelines_082725": seeds.apex,
    "Advantage++Broker+2025": seeds.advantage_plus,
    "2025 Program Guidelines UPDATED": seeds.citizens,
    "112025 Rates - STANDARD": seeds.falcon,
}
# (provider, pdf stem, sample) where the extractor chose a different but defensible program
# structure, so the matched-tier position is not comparable. Each is on the review checklist.
STRUCTURAL_DIFFERENCES = {
    # Reads "$75,000 ALL IN" as an app-only note instead of a hard Tier 1 cap -> Tier 1 not 3.
    ("openai", "2025 Program Guidelines UPDATED", "strong"),
    ("openai", "2025 Program Guidelines UPDATED", "trucking"),
    # Models the A-E credit-rating grid as five programs; the seed collapses it to one box.
    ("openai", "112025 Rates - STANDARD", "strong"),
    ("openai", "112025 Rates - STANDARD", "trucking"),
}

FEATURES = {
    s["key"]: derive_features(application_input_from_payload(s), today=date(2026, 1, 1))
    for s in samples.SAMPLES
}
CASES = [
    (provider.name, stem)
    for provider in sorted(LIVE.iterdir())
    if provider.is_dir()
    for stem in SEEDS
    if (provider / f"{stem}.json").exists()
]


def _position(result: LenderEvaluation) -> str:
    if not result.eligible:
        return "ineligible"
    rank = next(p.rank for p in result.programs if p.name == result.matched_program)
    applicable = sorted(p.rank for p in result.programs if p.applicable)
    return f"eligible@{applicable.index(rank) + 1}"


def _policies(provider: str, stem: str) -> tuple[Policy, Policy, Any]:
    extracted = ExtractedPolicy.model_validate_json((LIVE / provider / f"{stem}.json").read_text())
    draft = build_draft(extracted)
    live = Policy.model_validate({"lender_id": "l", "lender_name": "l", **draft.policy})
    hand = Policy.model_validate({"lender_id": "h", "lender_name": "h", **SEEDS[stem]()["policy"]})
    return live, hand, draft


@pytest.mark.skipif(not CASES, reason="no recorded live extractions")
@pytest.mark.parametrize(("provider", "stem"), CASES, ids=[f"{p}:{s}" for p, s in CASES])
def test_every_extracted_rule_is_evaluable(provider: str, stem: str) -> None:
    _, _, draft = _policies(provider, stem)
    assert draft.dropped == [], [u.reason for u in draft.dropped]
    assert draft.policy["programs"], "an extraction with no programs is useless"


@pytest.mark.skipif(not CASES, reason="no recorded live extractions")
@pytest.mark.parametrize(("provider", "stem"), CASES, ids=[f"{p}:{s}" for p, s in CASES])
def test_extracted_policy_agrees_with_the_seed(provider: str, stem: str) -> None:
    live, hand, _ = _policies(provider, stem)
    for key, features in FEATURES.items():
        got, want = evaluate_lender(live, features), evaluate_lender(hand, features)
        assert got.eligible == want.eligible, (
            f"{key}: {got.rejection_reasons or got.matched_program}"
        )
        if (provider, stem, key) not in STRUCTURAL_DIFFERENCES:
            assert _position(got) == _position(want), key


# --- the coercion that made the live responses usable ---------------------------------------


def value(**slot: Any) -> object:
    return ExtractedValue(number=None, text=None, boolean=None, options=None, range=None)\
        .model_copy(update=slot).resolve()  # fmt: skip


@pytest.mark.parametrize(
    ("operator", "raw", "expected"),
    [
        ("eq", ["CA"], "CA"),  # one option in the list slot + scalar operator (the common case)
        ("neq", ["private_party"], "private_party"),
        ("not_in", "CA", ["CA"]),  # scalar in the text slot + list operator
        ("in", ["TX", "OK"], ["TX", "OK"]),  # already right
        ("gte", 700, 700),
        ("between", [10000, 75000], [10000, 75000]),
        ("is_true", True, None),  # no-value operators carry no value
        ("eq", ["CA", "NV"], ["CA", "NV"]),  # ambiguous: left for the validator to reject
    ],
)
def test_coerce_bends_values_to_the_operator_shape(
    operator: str, raw: object, expected: object
) -> None:
    assert _coerce(operator, raw) == expected


def test_value_slots_resolve_in_priority_order() -> None:
    assert value(number=5) == 5
    assert value(options=["a"]) == ["a"]
    assert value(range=[1, 2]) == [1, 2]
    assert value() is None
