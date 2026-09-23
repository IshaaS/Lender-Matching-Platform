import logging
import uuid
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.errors import fail
from app.config import get_settings
from app.db import get_session
from app.models import IngestionJob, Lender
from app.models.enums import IngestionStatus
from app.schemas.ingestion import IngestionJobOut
from app.services import ingestion
from app.services.ingestion import InvalidUploadError

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/ingestion", tags=["lender onboarding"])


def _out(session: Session, job: IngestionJob) -> IngestionJobOut:
    out = IngestionJobOut.model_validate(job)
    if job.lender_id:
        lender = session.get(Lender, job.lender_id)
        out.lender_name = lender.name if lender else None
    return out


@router.post("", response_model=IngestionJobOut, status_code=202)
async def upload_guidelines(
    background: BackgroundTasks,
    file: Annotated[UploadFile, File(description="A lender guideline PDF")],
    lender_id: Annotated[uuid.UUID | None, Form()] = None,
    new_lender_name: Annotated[str | None, Form()] = None,
    session: Session = Depends(get_session),
) -> IngestionJobOut:
    """Uploads a PDF and starts extraction. The result is a DRAFT policy version for review;
    nothing is published automatically. Poll GET /ingestion/{id} for progress."""
    content = await file.read()
    use_hatchet = get_settings().use_hatchet
    try:
        job = ingestion.store_upload(
            session,
            filename=file.filename or "upload.pdf",
            content=content,
            lender_id=lender_id,
            new_lender_name=new_lender_name,
            mode="hatchet" if use_hatchet else "sync",
        )
    except InvalidUploadError as error:
        fail(422, str(error))
    session.commit()

    if use_hatchet and not _dispatch_to_hatchet(job, session):
        use_hatchet = False
    if not use_hatchet:
        background.add_task(ingestion.execute_job, job.id)
    return _out(session, job)


def _dispatch_to_hatchet(job: IngestionJob, session: Session) -> bool:
    try:
        from app.workflows.ingestion import IngestionInput, ingestion_workflow

        ref = ingestion_workflow.run_no_wait(IngestionInput(job_id=str(job.id)))
        job.workflow_run_id = ref.workflow_run_id
        session.commit()
        return True
    except Exception:  # noqa: BLE001
        logger.exception("Could not dispatch job %s to Hatchet; running in-process", job.id)
        job.mode = "sync"
        session.commit()
        return False


@router.get("", response_model=list[IngestionJobOut])
def list_jobs(session: Session = Depends(get_session)) -> list[IngestionJobOut]:
    jobs = session.scalars(select(IngestionJob).order_by(IngestionJob.created_at.desc()))
    return [_out(session, job) for job in jobs]


@router.get("/{job_id}", response_model=IngestionJobOut)
def read_job(job_id: uuid.UUID, session: Session = Depends(get_session)) -> IngestionJobOut:
    job = session.get(IngestionJob, job_id, populate_existing=True)
    if job is None:
        fail(404, "Ingestion job not found.")
    return _out(session, job)


@router.post("/{job_id}/retry", response_model=IngestionJobOut, status_code=202)
def retry_job(
    job_id: uuid.UUID, background: BackgroundTasks, session: Session = Depends(get_session)
) -> IngestionJobOut:
    job = session.get(IngestionJob, job_id)
    if job is None:
        fail(404, "Ingestion job not found.")
    if job.status != IngestionStatus.FAILED:
        fail(409, f"Only failed jobs can be retried; this one is {job.status}.")
    job.status, job.error = IngestionStatus.UPLOADED, None
    session.commit()
    background.add_task(ingestion.execute_job, job.id)
    return _out(session, job)
