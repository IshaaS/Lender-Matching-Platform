import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base
from app.models.base import JSONBType, JsonValue, TimestampMixin, uuid_pk
from app.models.enums import PolicyStatus


class Lender(Base, TimestampMixin):
    __tablename__ = "lenders"

    id: Mapped[uuid.UUID] = uuid_pk()
    name: Mapped[str] = mapped_column(String(200), unique=True)
    slug: Mapped[str] = mapped_column(String(80), unique=True)
    contact_name: Mapped[str | None] = mapped_column(String(200))
    contact_email: Mapped[str | None] = mapped_column(String(200))
    contact_phone: Mapped[str | None] = mapped_column(String(50))
    # Lenders with past results are deactivated, never deleted.
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    policy_versions: Mapped[list["PolicyVersion"]] = relationship(
        back_populates="lender",
        cascade="all, delete-orphan",
        order_by="PolicyVersion.version_number.desc()",
    )


class PolicyVersion(Base, TimestampMixin):
    """A snapshot of one lender's credit policy. Match results point at the exact version
    they were evaluated against, so publishing a new version never rewrites history."""

    __tablename__ = "policy_versions"
    __table_args__ = (
        UniqueConstraint("lender_id", "version_number", name="uq_policy_versions_lender_version"),
        # At most one published and one draft version per lender.
        Index(
            "uq_policy_versions_one_published",
            "lender_id",
            unique=True,
            postgresql_where=text("status = 'published'"),
        ),
        Index(
            "uq_policy_versions_one_draft",
            "lender_id",
            unique=True,
            postgresql_where=text("status = 'draft'"),
        ),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    lender_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("lenders.id", ondelete="CASCADE"), index=True
    )
    version_number: Mapped[int] = mapped_column(Integer)
    status: Mapped[PolicyStatus] = mapped_column(String(20), default=PolicyStatus.DRAFT)
    source_document: Mapped[str | None] = mapped_column(String(300))
    notes: Mapped[str | None] = mapped_column(Text)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    lender: Mapped[Lender] = relationship(back_populates="policy_versions")
    programs: Mapped[list["Program"]] = relationship(
        back_populates="policy_version", cascade="all, delete-orphan", order_by="Program.rank"
    )
    rules: Mapped[list["PolicyRule"]] = relationship(
        back_populates="policy_version",
        cascade="all, delete-orphan",
        order_by="PolicyRule.sort_order",
    )


class Program(Base, TimestampMixin):
    """A tier / credit box within a policy. Rank 1 is the most favourable."""

    __tablename__ = "programs"
    __table_args__ = (
        CheckConstraint("rank >= 1", name="ck_programs_rank_positive"),
        UniqueConstraint("policy_version_id", "rank", name="uq_programs_policy_version_rank"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    policy_version_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("policy_versions.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(120))
    rank: Mapped[int] = mapped_column(Integer)
    decision_mode: Mapped[str] = mapped_column(String(32), default="automatic")
    description: Mapped[str | None] = mapped_column(Text)
    # Conditions deciding whether this program is even considered for an application,
    # e.g. Stearns "No PayNet" tiers only apply when has_paynet is false.
    applies_when: Mapped[JsonValue] = mapped_column(JSONBType, default=list)
    # Display-only metadata: rate bands, documents required, max commission, etc.
    details: Mapped[JsonValue] = mapped_column(JSONBType, default=dict)

    policy_version: Mapped[PolicyVersion] = relationship(back_populates="programs")
    rules: Mapped[list["PolicyRule"]] = relationship(
        back_populates="program", cascade="all, delete-orphan", order_by="PolicyRule.sort_order"
    )


class PolicyRule(Base, TimestampMixin):
    """One check. `program_id IS NULL` means a lender-wide restriction.

    kind = "simple": field_key / operator / value.
    kind = "any_of": passes when any entry in `alternatives` passes (each entry is a
    {field, operator, value, label} condition).
    """

    __tablename__ = "policy_rules"
    __table_args__ = (
        CheckConstraint("severity IN ('hard', 'soft')", name="ck_policy_rules_severity"),
        CheckConstraint("kind IN ('simple', 'any_of')", name="ck_policy_rules_kind"),
        CheckConstraint(
            "(kind = 'simple' AND field_key IS NOT NULL AND operator IS NOT NULL)"
            " OR (kind = 'any_of' AND jsonb_array_length(alternatives) > 0)",
            name="ck_policy_rules_kind_shape",
        ),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    policy_version_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("policy_versions.id", ondelete="CASCADE"), index=True
    )
    program_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("programs.id", ondelete="CASCADE"), index=True
    )
    kind: Mapped[str] = mapped_column(String(20), default="simple")
    label: Mapped[str] = mapped_column(String(200))
    category: Mapped[str] = mapped_column(String(30), default="other")
    severity: Mapped[str] = mapped_column(String(10), default="hard")

    field_key: Mapped[str | None] = mapped_column(String(80))
    operator: Mapped[str | None] = mapped_column(String(30))
    value: Mapped[JsonValue] = mapped_column(JSONBType, nullable=True)
    alternatives: Mapped[JsonValue] = mapped_column(JSONBType, default=list)

    applies_when: Mapped[JsonValue] = mapped_column(JSONBType, default=list)
    # Optional override; the engine generates a message from operator + values otherwise.
    message_template: Mapped[str | None] = mapped_column(Text)

    # Provenance
    source_document: Mapped[str | None] = mapped_column(String(300))
    source_quote: Mapped[str | None] = mapped_column(Text)
    source_page: Mapped[int | None] = mapped_column(Integer)

    sort_order: Mapped[int] = mapped_column(Integer, default=0)

    policy_version: Mapped[PolicyVersion] = relationship(back_populates="rules")
    program: Mapped[Program | None] = relationship(back_populates="rules")
