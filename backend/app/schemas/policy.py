import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import PolicyStatus
from app.schemas.ingestion import ExtractionReview


class ConditionIn(BaseModel):
    field: str
    operator: str
    value: Any = None
    label: str | None = None


class RuleIn(BaseModel):
    """Shape is validated here; meaning (field/operator/value compatibility) is validated by
    the engine's Rule model before anything is saved."""

    program_id: uuid.UUID | None = None
    kind: Literal["simple", "any_of"] = "simple"
    label: str = Field(min_length=1, max_length=200)
    category: str = "other"
    severity: Literal["hard", "soft"] = "hard"
    field: str | None = None
    operator: str | None = None
    value: Any = None
    alternatives: list[ConditionIn] = Field(default_factory=list)
    applies_when: list[ConditionIn] = Field(default_factory=list)
    message_template: str | None = None
    source_document: str | None = None
    source_quote: str | None = None
    source_page: int | None = None
    sort_order: int | None = None


class RuleOut(BaseModel):
    id: uuid.UUID
    program_id: uuid.UUID | None
    kind: str
    label: str
    category: str
    severity: str
    field: str | None
    operator: str | None
    value: Any
    alternatives: list[dict[str, Any]]
    applies_when: list[dict[str, Any]]
    message_template: str | None
    source_document: str | None = None
    source_quote: str | None = None
    source_page: int | None = None
    sort_order: int
    # Plain-English rendering, e.g. "FICO score at least 700".
    summary: str


class ProgramIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    rank: int = Field(ge=1)
    decision_mode: Literal["automatic", "manual_review"] = "automatic"
    description: str | None = None
    applies_when: list[ConditionIn] = Field(default_factory=list)
    details: dict[str, Any] = Field(default_factory=dict)


class ProgramPatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    rank: int | None = Field(default=None, ge=1)
    decision_mode: Literal["automatic", "manual_review"] | None = None
    description: str | None = None
    applies_when: list[ConditionIn] | None = None
    details: dict[str, Any] | None = None


class ProgramOut(BaseModel):
    id: uuid.UUID
    name: str
    rank: int
    decision_mode: str = "automatic"
    description: str | None
    applies_when: list[dict[str, Any]]
    applies_when_summary: list[str]
    details: dict[str, Any]
    rules: list[RuleOut]


class PolicyVersionSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    version_number: int
    status: PolicyStatus
    source_document: str | None
    notes: str | None
    published_at: datetime | None
    created_at: datetime
    updated_at: datetime


class PolicyVersionOut(PolicyVersionSummary):
    lender_id: uuid.UUID
    lender_name: str
    rules: list[RuleOut]
    programs: list[ProgramOut]
    # Empty when the version can be published / evaluated.
    validation_errors: list[str] = Field(default_factory=list)
    # Present when this version was produced by PDF ingestion: the reviewer's checklist.
    extraction: ExtractionReview | None = None


class LenderIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    contact_name: str | None = None
    contact_email: str | None = None
    contact_phone: str | None = None


class LenderPatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    contact_name: str | None = None
    contact_email: str | None = None
    contact_phone: str | None = None
    is_active: bool | None = None


class LenderOut(BaseModel):
    id: uuid.UUID
    name: str
    slug: str
    contact_name: str | None
    contact_email: str | None
    contact_phone: str | None
    is_active: bool
    published_version: PolicyVersionSummary | None
    draft_version: PolicyVersionSummary | None
    program_count: int
    rule_count: int
    updated_at: datetime
