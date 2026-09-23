import uuid
from datetime import date
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, CheckConstraint, Date, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base
from app.models.base import TimestampMixin, uuid_pk
from app.models.enums import ApplicationStatus, EquipmentCondition, TransactionType

if TYPE_CHECKING:
    from app.models.underwriting import UnderwritingRun

# Draft applications may be incomplete, so almost every borrower-supplied column is
# nullable. Completeness is enforced on submit (services.completeness), not by the schema.


class Business(Base, TimestampMixin):
    __tablename__ = "businesses"

    id: Mapped[uuid.UUID] = uuid_pk()
    legal_name: Mapped[str | None] = mapped_column(String(200))
    entity_type: Mapped[str | None] = mapped_column(String(50))
    state: Mapped[str | None] = mapped_column(String(2))
    industry: Mapped[str | None] = mapped_column(String(60))
    years_in_business: Mapped[Decimal | None] = mapped_column(Numeric(5, 1))
    annual_revenue: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    has_physical_location: Mapped[bool | None] = mapped_column(Boolean)
    is_us_based: Mapped[bool | None] = mapped_column(Boolean)
    # Falcon / Citizens trucking rules depend on fleet size.
    trucks_operated: Mapped[int | None] = mapped_column(Integer)

    application: Mapped["LoanApplication"] = relationship(back_populates="business")


class LoanApplication(Base, TimestampMixin):
    __tablename__ = "loan_applications"
    __table_args__ = (
        CheckConstraint(
            "amount IS NULL OR amount > 0", name="ck_loan_applications_amount_positive"
        ),
        CheckConstraint(
            "term_months IS NULL OR term_months > 0", name="ck_loan_applications_term_positive"
        ),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    business_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("businesses.id", ondelete="CASCADE"), unique=True
    )
    status: Mapped[ApplicationStatus] = mapped_column(
        String(20), default=ApplicationStatus.DRAFT, index=True
    )

    # Loan request
    amount: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    term_months: Mapped[int | None] = mapped_column(Integer)
    transaction_type: Mapped[TransactionType | None] = mapped_column(String(30))
    down_payment_pct: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    soft_cost_pct: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    # True when no owner will personally guarantee ("Corp only" programs).
    corp_only: Mapped[bool] = mapped_column(Boolean, default=False)
    notes: Mapped[str | None] = mapped_column(Text)

    business: Mapped[Business] = relationship(
        back_populates="application", cascade="all, delete-orphan", single_parent=True
    )
    guarantors: Mapped[list["Guarantor"]] = relationship(
        back_populates="application", cascade="all, delete-orphan", order_by="Guarantor.created_at"
    )
    business_credit: Mapped["BusinessCreditProfile | None"] = relationship(
        back_populates="application", cascade="all, delete-orphan", uselist=False
    )
    equipment_items: Mapped[list["EquipmentItem"]] = relationship(
        back_populates="application",
        cascade="all, delete-orphan",
        order_by="EquipmentItem.created_at",
    )
    runs: Mapped[list["UnderwritingRun"]] = relationship(
        cascade="all, delete-orphan", order_by="UnderwritingRun.created_at"
    )


class Guarantor(Base, TimestampMixin):
    __tablename__ = "guarantors"
    __table_args__ = (
        CheckConstraint(
            "fico_score IS NULL OR fico_score BETWEEN 300 AND 850", name="ck_guarantors_fico_range"
        ),
        CheckConstraint(
            "ownership_pct IS NULL OR ownership_pct BETWEEN 0 AND 100",
            name="ck_guarantors_ownership_range",
        ),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    application_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("loan_applications.id", ondelete="CASCADE"), index=True
    )
    full_name: Mapped[str | None] = mapped_column(String(200))
    ownership_pct: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    fico_score: Mapped[int | None] = mapped_column(Integer)
    is_homeowner: Mapped[bool | None] = mapped_column(Boolean)
    years_at_residence: Mapped[Decimal | None] = mapped_column(Numeric(4, 1))
    is_us_citizen: Mapped[bool | None] = mapped_column(Boolean)
    industry_experience_years: Mapped[Decimal | None] = mapped_column(Numeric(4, 1))

    has_cdl: Mapped[bool | None] = mapped_column(Boolean)
    cdl_class: Mapped[str | None] = mapped_column(String(1))
    cdl_years: Mapped[Decimal | None] = mapped_column(Numeric(4, 1))

    is_licensed_medical_professional: Mapped[bool | None] = mapped_column(Boolean)
    years_licensed: Mapped[Decimal | None] = mapped_column(Numeric(4, 1))

    # Revolving / unsecured debt (Stearns utilisation rule, Apex "50% revolving available")
    revolving_credit_limit: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    revolving_balance: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    unsecured_debt: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))

    # Derogatory history
    has_bankruptcy: Mapped[bool] = mapped_column(Boolean, default=False)
    bankruptcy_discharge_date: Mapped[date | None] = mapped_column(Date)
    has_judgments: Mapped[bool] = mapped_column(Boolean, default=False)
    has_foreclosures: Mapped[bool] = mapped_column(Boolean, default=False)
    has_repossessions: Mapped[bool] = mapped_column(Boolean, default=False)
    has_tax_liens: Mapped[bool] = mapped_column(Boolean, default=False)
    has_recent_collections: Mapped[bool] = mapped_column(Boolean, default=False)

    application: Mapped[LoanApplication] = relationship(back_populates="guarantors")


class BusinessCreditProfile(Base, TimestampMixin):
    __tablename__ = "business_credit_profiles"

    id: Mapped[uuid.UUID] = uuid_pk()
    application_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("loan_applications.id", ondelete="CASCADE"), unique=True
    )
    # NULL is meaningful: several lenders publish alternative tiers for "no PayNet".
    paynet_score: Mapped[int | None] = mapped_column(Integer)
    trade_lines_count: Mapped[int | None] = mapped_column(Integer)
    trade_history_years: Mapped[Decimal | None] = mapped_column(Numeric(4, 1))
    largest_comparable_credit: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    comparable_contracts_count: Mapped[int | None] = mapped_column(Integer)
    clean_payment_history_months: Mapped[int | None] = mapped_column(Integer)

    application: Mapped[LoanApplication] = relationship(back_populates="business_credit")


class EquipmentItem(Base, TimestampMixin):
    __tablename__ = "equipment_items"

    id: Mapped[uuid.UUID] = uuid_pk()
    application_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("loan_applications.id", ondelete="CASCADE"), index=True
    )
    category: Mapped[str | None] = mapped_column(String(60))
    description: Mapped[str | None] = mapped_column(String(300))
    model_year: Mapped[int | None] = mapped_column(Integer)
    condition: Mapped[EquipmentCondition | None] = mapped_column(String(10))
    mileage: Mapped[int | None] = mapped_column(Integer)
    hours: Mapped[int | None] = mapped_column(Integer)
    is_titled: Mapped[bool | None] = mapped_column(Boolean)

    application: Mapped[LoanApplication] = relationship(back_populates="equipment_items")
