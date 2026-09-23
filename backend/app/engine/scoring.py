"""Fit score (0-100) for an eligible lender.

  tier      40  how good the matched program is among those the borrower could apply for
  headroom  40  how comfortably numeric minimums/maximums are cleared (thin margins = lower)
  soft      20  share of the lender's stated preferences that are met

Weights are constants here so they are easy to find and tune.
"""

from typing import TYPE_CHECKING

from pydantic import BaseModel

from app.engine.catalog import get_field
from app.engine.operators import get_operator

if TYPE_CHECKING:
    from app.engine.evaluator import CriterionOutcome

TIER_WEIGHT = 40
HEADROOM_WEIGHT = 40
SOFT_WEIGHT = 20
DEFAULT_HEADROOM_FRACTION = 0.25
# With no numeric criteria / no preferences there is nothing to judge: stay neutral-positive.
NEUTRAL_HEADROOM = 0.5
NEUTRAL_SOFT = 0.5


class ScoreBreakdown(BaseModel):
    tier: float
    headroom: float
    soft: float
    total: int
    notes: list[str] = []


def _headroom(criterion: "CriterionOutcome") -> float | None:
    if criterion.field is None or criterion.operator is None:
        return None
    direction = get_operator(criterion.operator).direction
    actual, expected = criterion.actual, criterion.expected
    if (
        direction == 0
        or not isinstance(actual, int | float)
        or not isinstance(expected, int | float)
    ):
        return None
    span = get_field(criterion.field).headroom_span or abs(expected) * DEFAULT_HEADROOM_FRACTION
    if span <= 0:
        return None
    return max(0.0, min(1.0, (actual - expected) * direction / span))


def score_match(
    position: int, program_count: int, criteria: list["CriterionOutcome"]
) -> ScoreBreakdown:
    # Tier 1 gets 1.0 (40 points) for all lenders regardless of total program count.
    # Subsequent tiers step down by 0.25.
    tier_ratio = max(0.2, 1.0 - 0.25 * position)

    hard_passed = [c for c in criteria if c.severity == "hard" and c.outcome == "passed"]
    margins = [m for m in map(_headroom, hard_passed) if m is not None]
    headroom_ratio = sum(margins) / len(margins) if margins else NEUTRAL_HEADROOM

    soft = [c for c in criteria if c.severity == "soft" and c.outcome != "skipped"]
    soft_ratio = sum(c.outcome == "passed" for c in soft) / len(soft) if soft else NEUTRAL_SOFT

    tier = round(TIER_WEIGHT * tier_ratio, 1)
    headroom = round(HEADROOM_WEIGHT * headroom_ratio, 1)
    soft_points = round(SOFT_WEIGHT * soft_ratio, 1)
    notes = [
        f"Matched program {position + 1} of {program_count} available",
        f"Average headroom over {len(margins)} numeric criteria: {headroom_ratio:.0%}"
        if margins
        else "No numeric criteria to measure headroom",
        f"{sum(c.outcome == 'passed' for c in soft)}/{len(soft)} lender preferences met"
        if soft
        else "Lender states no soft preferences",
    ]
    return ScoreBreakdown(
        tier=tier,
        headroom=headroom,
        soft=soft_points,
        total=max(0, min(100, round(tier + headroom + soft_points))),
        notes=notes,
    )
