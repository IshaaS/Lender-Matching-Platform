"""PDF ingestion pipeline: upload -> extract text -> extract policy -> create draft.

Like underwriting, every step is a plain function shared by the in-process runner and the
Hatchet workflow. Nothing extracted is ever published: the output is always a draft version
for a human to review in the policy editor.
"""

import logging
import uuid
from datetime import UTC, datetime
from io import BytesIO
from pathlib import Path

from pypdf import PdfReader
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import SessionLocal
from app.models import IngestionJob, Lender, PolicyVersion
from app.models.enums import IngestionStatus, PolicyStatus
from app.services import policies
from app.services.extraction import (
    ExtractedPolicy,
    ExtractionError,
    build_draft,
    get_extractor,
)
from app.services.policy_mapper import populate_version

logger = logging.getLogger(__name__)

MAX_UPLOAD_BYTES = 20 * 1024 * 1024


class InvalidUploadError(Exception):
    pass


# --- step 0: upload ---------------------------------------------------------------------------


def store_upload(
    session: Session,
    *,
    filename: str,
    content: bytes,
    lender_id: uuid.UUID | None,
    new_lender_name: str | None,
    mode: str,
) -> IngestionJob:
    if not content.startswith(b"%PDF"):
        raise InvalidUploadError("Only PDF files are accepted.")
    if len(content) > MAX_UPLOAD_BYTES:
        raise InvalidUploadError("PDF is larger than 20 MB.")
    if lender_id is None and not (new_lender_name or "").strip():
        raise InvalidUploadError("Choose an existing lender or give the new lender a name.")
    if lender_id is not None:
        existing = session.get(Lender, lender_id)
        if existing is None:
            raise InvalidUploadError("Lender not found.")
        if policies.get_version(existing, PolicyStatus.DRAFT):
            raise InvalidUploadError(
                f"{existing.name} already has a draft. Publish or discard it before ingesting."
            )

    job = IngestionJob(
        lender_id=lender_id,
        new_lender_name=(new_lender_name or "").strip() or None,
        filename=Path(filename).name or "upload.pdf",
        storage_path="",
        status=IngestionStatus.UPLOADED,
        mode=mode,
    )
    session.add(job)
    session.flush()

    uploads = Path(get_settings().uploads_dir)
    uploads.mkdir(parents=True, exist_ok=True)
    path = uploads / f"{job.id}.pdf"
    path.write_bytes(content)
    job.storage_path = str(path)
    return job


# --- step 1: text ------------------------------------------------------------------------------


def extract_text(pdf_bytes: bytes) -> str:
    """Plain text for the record and for search; the model sees the PDF itself."""
    reader = PdfReader(BytesIO(pdf_bytes))
    return "\n\n".join((page.extract_text() or "").strip() for page in reader.pages)


def mark_extracting(session: Session, job_id: uuid.UUID) -> IngestionJob:
    job = session.get(IngestionJob, job_id)
    if job is None:
        raise LookupError(f"Ingestion job {job_id} not found")
    job.status, job.error = IngestionStatus.EXTRACTING, None
    if job.extracted_text is None:
        job.extracted_text = extract_text(Path(job.storage_path).read_bytes())
    session.commit()
    return job


# --- step 2: policy ---------------------------------------------------------------------------


def extract_policy(job: IngestionJob) -> ExtractedPolicy:
    extractor = get_extractor()
    logger.info("Extracting %s with the %s extractor", job.filename, extractor.name)
    return extractor.extract(
        Path(job.storage_path).read_bytes(), job.extracted_text or "", job.filename
    )


# --- step 3: draft ----------------------------------------------------------------------------


def create_draft(
    session: Session, job_id: uuid.UUID, extracted: ExtractedPolicy, extractor_name: str
) -> PolicyVersion:
    job = session.get(IngestionJob, job_id)
    if job is None:
        raise LookupError(f"Ingestion job {job_id} not found")

    if job.lender_id is None:
        name = job.new_lender_name or extracted.lender_name
        slug = policies.slugify(name)
        existing = session.scalar(
            select(Lender).where((Lender.name == name) | (Lender.slug == slug))
        )
        if existing is not None:
            # The uploader typed a name that already exists: attach to it rather than fail.
            lender = existing
        else:
            lender = Lender(
                name=name,
                slug=slug,
                contact_name=extracted.contact_name,
                contact_email=extracted.contact_email,
                contact_phone=extracted.contact_phone,
            )
            session.add(lender)
            session.flush()
        job.lender_id = lender.id
    else:
        found = session.get(Lender, job.lender_id)
        assert found is not None
        lender = found

    # A draft created by an earlier failed attempt of this job is replaced, so retries are safe.
    stale = policies.get_version(lender, PolicyStatus.DRAFT)
    if stale is not None and job.policy_version_id == stale.id:
        session.delete(stale)
        session.flush()
    elif stale is not None:
        raise ExtractionError(f"{lender.name} already has a draft; discard it and retry.")

    draft = policies.create_draft(session, lender)
    draft.rules.clear()
    draft.programs.clear()
    result = build_draft(extracted)
    populate_version(draft, result.policy)
    draft.source_document = job.filename
    draft.notes = (
        f"Extracted from {job.filename} by the {extractor_name} extractor. "
        "Review the checklist before publishing."
    )

    job.extracted_policy = extracted.model_dump()
    job.uncertainties = [u.model_dump() for u in (*extracted.uncertainties, *result.dropped)]
    job.extractor = extractor_name
    job.policy_version_id = draft.id
    job.status = IngestionStatus.DRAFT_READY
    job.completed_at = datetime.now(UTC)
    session.commit()
    return draft


def fail_job(job_id: uuid.UUID, error: str) -> None:
    with SessionLocal() as session:
        job = session.get(IngestionJob, job_id)
        if job is None:
            return
        job.status = IngestionStatus.FAILED
        job.error = error[:2000]
        job.completed_at = datetime.now(UTC)
        session.commit()


# --- in-process driver ------------------------------------------------------------------------


def execute_job(job_id: uuid.UUID) -> None:
    try:
        with SessionLocal() as session:
            job = mark_extracting(session, job_id)
            extracted = extract_policy(job)
            extractor_name = get_extractor().name
            create_draft(session, job_id, extracted, extractor_name)
    except Exception as error:  # noqa: BLE001
        logger.exception("Ingestion job %s failed", job_id)
        fail_job(job_id, str(error))
