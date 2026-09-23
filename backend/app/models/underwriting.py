import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, Numeric, String, Text, text
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base
from app.models.base import JSONBType, JsonValue, TimestampMixin, uuid_pk
from app.models.enums import MatchStatus, RunMode, RunStatus


class UnderwritingRun(Base, TimestampMixin):
    __tablename__ = "underwriting_runs"
    __table_args__ = (
        Index(
            "uq_active_underwriting_run_per_application",
            "application_id",
            unique=True,
            postgresql_where=text("status IN ('queued', 'running')"),
        ),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    application_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("loan_applications.id", ondelete="CASCADE"), index=True
    )
    status: Mapped[RunStatus] = mapped_column(String(20), default=RunStatus.QUEUED, index=True)
    mode: Mapped[RunMode] = mapped_column(String(20))
    workflow_run_id: Mapped[str | None] = mapped_column(String(100))
    error: Mapped[str | None] = mapped_column(Text)
    # Derived features exactly as the engine saw them, so a result can always be explained.
    feature_snapshot: Mapped[JsonValue] = mapped_column(JSONBType, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    results: Mapped[list["LenderMatchResult"]] = relationship(
        back_populates="run", cascade="all, delete-orphan", order_by="LenderMatchResult.rank"
    )


class LenderMatchResult(Base, TimestampMixin):
    __tablename__ = "lender_match_results"

    id: Mapped[uuid.UUID] = uuid_pk()
    run_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("underwriting_runs.id", ondelete="CASCADE"), index=True
    )
    lender_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("lenders.id"))
    policy_version_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("policy_versions.id")
    )
    # Names are denormalised on purpose: results must stay readable after policy edits.
    lender_name: Mapped[str] = mapped_column(String(200))
    policy_version_number: Mapped[int] = mapped_column(Integer)

    status: Mapped[MatchStatus] = mapped_column(String(20), default=MatchStatus.EVALUATED)
    error: Mapped[str | None] = mapped_column(Text)
    eligible: Mapped[bool] = mapped_column(Boolean, default=False)
    decision: Mapped[str] = mapped_column(String(32), default="ineligible")
    matched_program_name: Mapped[str | None] = mapped_column(String(120))
    fit_score: Mapped[int] = mapped_column(Integer, default=0)
    score_breakdown: Mapped[JsonValue] = mapped_column(JSONBType, default=dict)
    # Share of hard rules passed on the closest program; ranks ineligible lenders.
    near_miss_ratio: Mapped[Decimal] = mapped_column(Numeric(4, 3), default=0)
    rejection_reasons: Mapped[JsonValue] = mapped_column(JSONBType, default=list)
    program_details: Mapped[JsonValue] = mapped_column(JSONBType, default=dict)
    # One entry per program: applicable?, eligible?, hard failure count. Powers "why not Tier 1?".
    program_summaries: Mapped[JsonValue] = mapped_column(JSONBType, default=list)
    rank: Mapped[int] = mapped_column(Integer, default=0)

    run: Mapped[UnderwritingRun] = relationship(back_populates="results")
    criteria: Mapped[list["CriterionResult"]] = relationship(
        back_populates="match_result",
        cascade="all, delete-orphan",
        order_by="CriterionResult.sort_order",
    )


class CriterionResult(Base):
    __tablename__ = "criterion_results"

    id: Mapped[uuid.UUID] = uuid_pk()
    match_result_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("lender_match_results.id", ondelete="CASCADE"),
        index=True,
    )
    # No FK to policy_rules: draft rules can be deleted, results must survive.
    rule_id: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True))
    # NULL = lender-wide restriction; otherwise the program the rule belongs to.
    program_name: Mapped[str | None] = mapped_column(String(120))
    program_rank: Mapped[int | None] = mapped_column(Integer)
    label: Mapped[str] = mapped_column(String(200))
    category: Mapped[str] = mapped_column(String(30))
    severity: Mapped[str] = mapped_column(String(10))
    outcome: Mapped[str] = mapped_column(String(20))  # passed | failed | skipped | missing
    field_key: Mapped[str | None] = mapped_column(String(80))
    operator: Mapped[str | None] = mapped_column(String(30))
    expected: Mapped[JsonValue] = mapped_column(JSONBType, nullable=True)
    actual: Mapped[JsonValue] = mapped_column(JSONBType, nullable=True)
    message: Mapped[str] = mapped_column(Text)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)

    match_result: Mapped[LenderMatchResult] = relationship(back_populates="criteria")
