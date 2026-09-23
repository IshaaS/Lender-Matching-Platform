import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models.base import JSONBType, JsonValue, TimestampMixin, uuid_pk
from app.models.enums import IngestionStatus


class IngestionJob(Base, TimestampMixin):
    """One uploaded lender guideline PDF on its way to becoming a draft policy.

    uploaded -> extracting -> draft_ready | failed
    """

    __tablename__ = "ingestion_jobs"

    id: Mapped[uuid.UUID] = uuid_pk()
    lender_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("lenders.id", ondelete="SET NULL"), index=True
    )
    # Set when the user is onboarding a lender that does not exist yet.
    new_lender_name: Mapped[str | None] = mapped_column(String(200))
    filename: Mapped[str] = mapped_column(String(300))
    storage_path: Mapped[str] = mapped_column(String(500))
    status: Mapped[IngestionStatus] = mapped_column(
        String(20), default=IngestionStatus.UPLOADED, index=True
    )
    mode: Mapped[str] = mapped_column(String(20), default="sync")
    workflow_run_id: Mapped[str | None] = mapped_column(String(100))
    error: Mapped[str | None] = mapped_column(Text)

    extracted_text: Mapped[str | None] = mapped_column(Text)
    # The extractor's raw structured answer, kept verbatim for audit.
    extracted_policy: Mapped[JsonValue] = mapped_column(JSONBType, nullable=True)
    # Items the extractor was unsure about; shown as a review checklist in the editor.
    uncertainties: Mapped[JsonValue] = mapped_column(JSONBType, default=list)
    extractor: Mapped[str | None] = mapped_column(String(80))

    policy_version_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("policy_versions.id", ondelete="SET NULL"), index=True
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
