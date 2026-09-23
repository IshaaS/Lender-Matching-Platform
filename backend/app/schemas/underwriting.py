import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class CriterionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    rule_id: uuid.UUID | None
    program_name: str | None
    program_rank: int | None
    label: str
    category: str
    severity: str
    outcome: str
    field_key: str | None
    operator: str | None
    expected: Any
    actual: Any
    message: str


class MatchResultSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    rank: int
    lender_id: uuid.UUID
    lender_name: str
    policy_version_id: uuid.UUID
    policy_version_number: int
    status: str
    error: str | None
    eligible: bool
    decision: str = "ineligible"
    matched_program_name: str | None
    fit_score: int
    score_breakdown: dict[str, Any]
    near_miss_ratio: float
    rejection_reasons: list[str]
    program_details: dict[str, Any]
    program_summaries: list[dict[str, Any]]


class MatchResultDetail(MatchResultSummary):
    criteria: list[CriterionOut]


class RunOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    application_id: uuid.UUID
    status: str
    mode: str
    error: str | None
    feature_snapshot: dict[str, Any] | None
    created_at: datetime
    started_at: datetime | None
    completed_at: datetime | None
    results: list[MatchResultSummary]
