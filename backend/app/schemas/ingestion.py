import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict

from app.models.enums import IngestionStatus


class IngestionJobOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    lender_id: uuid.UUID | None
    new_lender_name: str | None
    filename: str
    status: IngestionStatus
    mode: str
    error: str | None
    extractor: str | None
    uncertainties: list[dict[str, Any]]
    policy_version_id: uuid.UUID | None
    created_at: datetime
    completed_at: datetime | None
    # Filled by the API: the lender's name once known, for the jobs list.
    lender_name: str | None = None


class ExtractionReview(BaseModel):
    """Attached to a policy version that came from an ingestion job."""

    job_id: uuid.UUID
    filename: str
    extractor: str | None
    uncertainties: list[dict[str, Any]]
    completed_at: datetime | None
