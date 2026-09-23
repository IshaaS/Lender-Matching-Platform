import uuid
from collections.abc import Callable
from datetime import date, datetime
from typing import Annotated, Literal

from pydantic import AfterValidator, BaseModel, ConfigDict, Field

from app.engine.catalog import (
    ENTITY_TYPES,
    EQUIPMENT_CATEGORIES,
    INDUSTRIES,
    TRANSACTION_TYPES,
    US_STATES,
)
from app.models.enums import ApplicationStatus

# Drafts may be partial, so every field is optional here; completeness is checked on submit.
# Values that ARE present must still be valid, which is what these types enforce.
Money = Annotated[float, Field(ge=0, le=1_000_000_000)]
Percent = Annotated[float, Field(ge=0, le=100)]
Years = Annotated[float, Field(ge=0, le=150)]
Count = Annotated[int, Field(ge=0, le=100_000)]


def _one_of(options: tuple[str, ...]) -> Callable[[str], str]:
    def check(value: str) -> str:
        if value not in options:
            raise ValueError(f"'{value}' is not a valid option")
        return value

    return check


# Option lists come from the engine catalog so the form, the API and the rules always agree.
EntityType = Annotated[str, AfterValidator(_one_of(ENTITY_TYPES))]
State = Annotated[str, AfterValidator(_one_of(US_STATES))]
Industry = Annotated[str, AfterValidator(_one_of(INDUSTRIES))]
TransactionKind = Annotated[str, AfterValidator(_one_of(TRANSACTION_TYPES))]
EquipmentCategory = Annotated[str, AfterValidator(_one_of(EQUIPMENT_CATEGORIES))]


class BusinessPayload(BaseModel):
    legal_name: Annotated[str, Field(max_length=200)] | None = None
    entity_type: EntityType | None = None
    state: State | None = None
    industry: Industry | None = None
    years_in_business: Years | None = None
    annual_revenue: Money | None = None
    has_physical_location: bool | None = None
    is_us_based: bool | None = None
    trucks_operated: Count | None = None


class LoanPayload(BaseModel):
    amount: Annotated[float, Field(gt=0, le=1_000_000_000)] | None = None
    term_months: Annotated[int, Field(ge=1, le=240)] | None = None
    transaction_type: TransactionKind | None = None
    down_payment_pct: Percent | None = None
    soft_cost_pct: Percent | None = None
    corp_only: bool = False
    notes: Annotated[str, Field(max_length=2000)] | None = None


class BusinessCreditPayload(BaseModel):
    paynet_score: Annotated[int, Field(ge=300, le=900)] | None = None
    trade_lines_count: Count | None = None
    trade_history_years: Years | None = None
    largest_comparable_credit: Money | None = None
    comparable_contracts_count: Count | None = None
    clean_payment_history_months: Annotated[int, Field(ge=0, le=1200)] | None = None


class GuarantorPayload(BaseModel):
    full_name: Annotated[str, Field(max_length=200)] | None = None
    ownership_pct: Percent | None = None
    fico_score: Annotated[int, Field(ge=300, le=850)] | None = None
    is_homeowner: bool | None = None
    years_at_residence: Years | None = None
    is_us_citizen: bool | None = None
    industry_experience_years: Years | None = None
    has_cdl: bool | None = None
    cdl_class: Literal["A", "B", "C"] | None = None
    cdl_years: Years | None = None
    is_licensed_medical_professional: bool | None = None
    years_licensed: Years | None = None
    revolving_credit_limit: Money | None = None
    revolving_balance: Money | None = None
    unsecured_debt: Money | None = None
    has_bankruptcy: bool = False
    bankruptcy_discharge_date: date | None = None
    has_judgments: bool = False
    has_foreclosures: bool = False
    has_repossessions: bool = False
    has_tax_liens: bool = False
    has_recent_collections: bool = False


class EquipmentPayload(BaseModel):
    category: EquipmentCategory | None = None
    description: Annotated[str, Field(max_length=300)] | None = None
    model_year: Annotated[int, Field(ge=1950, le=2100)] | None = None
    condition: Literal["new", "used"] | None = None
    mileage: Annotated[int, Field(ge=0, le=5_000_000)] | None = None
    hours: Annotated[int, Field(ge=0, le=1_000_000)] | None = None
    is_titled: bool | None = None


class ApplicationPayload(BaseModel):
    business: BusinessPayload = Field(default_factory=BusinessPayload)
    loan: LoanPayload = Field(default_factory=LoanPayload)
    business_credit: BusinessCreditPayload = Field(default_factory=BusinessCreditPayload)
    guarantors: list[GuarantorPayload] = Field(default_factory=list, max_length=10)
    equipment: list[EquipmentPayload] = Field(default_factory=list, max_length=20)


class RunSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    status: str
    mode: str
    error: str | None
    created_at: datetime
    completed_at: datetime | None
    eligible_count: int = 0
    lender_count: int = 0
    best_lender: str | None = None
    best_program: str | None = None
    best_score: int | None = None


class ApplicationListItem(BaseModel):
    id: uuid.UUID
    status: ApplicationStatus
    legal_name: str | None
    industry: str | None
    state: str | None
    amount: float | None
    notes: str | None
    created_at: datetime
    updated_at: datetime
    latest_run: RunSummary | None = None


class ApplicationOut(ApplicationPayload):
    id: uuid.UUID
    status: ApplicationStatus
    created_at: datetime
    updated_at: datetime
    missing_fields: list["MissingField"] = Field(default_factory=list)
    latest_run: RunSummary | None = None


class MissingField(BaseModel):
    path: str
    label: str


class SampleApplication(BaseModel):
    key: str
    title: str
    payload: ApplicationPayload
