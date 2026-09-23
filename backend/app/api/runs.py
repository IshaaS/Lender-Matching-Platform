import logging
import uuid

from fastapi import APIRouter, BackgroundTasks, Depends
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.api.applications import get_application
from app.api.errors import fail
from app.config import get_settings
from app.db import get_session
from app.models import LenderMatchResult, UnderwritingRun
from app.models.enums import ApplicationStatus, RunMode
from app.schemas.underwriting import MatchResultDetail, RunOut
from app.services import underwriting
from app.services.application_mapper import to_payload
from app.services.completeness import missing_fields

logger = logging.getLogger(__name__)
router = APIRouter(tags=["underwriting"])


@router.post("/applications/{application_id}/runs", response_model=RunOut, status_code=202)
def start_run(
    application_id: uuid.UUID,
    background: BackgroundTasks,
    session: Session = Depends(get_session),
) -> UnderwritingRun:
    """Queues an underwriting run and returns immediately; poll GET /runs/{id} for status."""
    application = get_application(application_id, session)
    if application.status not in (ApplicationStatus.SUBMITTED, ApplicationStatus.COMPLETED):
        if application.status == ApplicationStatus.DRAFT:
            fail(
                409,
                "Draft applications cannot be underwritten directly. Submit the application first.",
            )
        if application.status == ApplicationStatus.UNDERWRITING:
            fail(409, "An underwriting run is already in progress for this application.")
        fail(409, f"Underwriting cannot start from application status '{application.status}'.")

    gaps = missing_fields(to_payload(application))
    if gaps:
        fail(422, f"{len(gaps)} required field(s) are missing.", gaps)

    use_hatchet = get_settings().use_hatchet
    run = underwriting.create_run(
        session, application, RunMode.HATCHET if use_hatchet else RunMode.SYNC
    )
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        fail(409, "An underwriting run is already in progress for this application.")

    if use_hatchet and not _dispatch_to_hatchet(run, session):
        use_hatchet = False
    if not use_hatchet:
        background.add_task(underwriting.execute_run, run.id)
    return _load_run(run.id, session)


def _dispatch_to_hatchet(run: UnderwritingRun, session: Session) -> bool:
    """Hands the run to the Hatchet workflow. Returns False (after switching the run to the
    in-process mode) if Hatchet cannot be reached, so an outage never blocks underwriting."""
    try:
        # Imported lazily: the Hatchet client cannot be constructed without a token.
        from app.workflows.underwriting import UnderwritingInput, underwriting_workflow

        ref = underwriting_workflow.run_no_wait(UnderwritingInput(run_id=str(run.id)))
        run.workflow_run_id = ref.workflow_run_id
        session.commit()
        return True
    except Exception:  # noqa: BLE001
        logger.exception("Could not dispatch run %s to Hatchet; running in-process", run.id)
        run.mode = RunMode.SYNC
        session.commit()
        return False


@router.get("/applications/{application_id}/runs", response_model=list[RunOut])
def list_runs(
    application_id: uuid.UUID, session: Session = Depends(get_session)
) -> list[UnderwritingRun]:
    get_application(application_id, session)
    return list(
        session.scalars(
            select(UnderwritingRun)
            .where(UnderwritingRun.application_id == application_id)
            .options(selectinload(UnderwritingRun.results))
            .order_by(UnderwritingRun.created_at.desc())
        )
    )


def _load_run(run_id: uuid.UUID, session: Session) -> UnderwritingRun:
    run = session.scalar(
        select(UnderwritingRun)
        .where(UnderwritingRun.id == run_id)
        .options(selectinload(UnderwritingRun.results))
        .execution_options(populate_existing=True)
    )
    if run is None:
        fail(404, "Underwriting run not found.")
    return run


@router.get("/runs/{run_id}", response_model=RunOut)
def read_run(run_id: uuid.UUID, session: Session = Depends(get_session)) -> UnderwritingRun:
    """Run status plus ranked lender results (without per-criterion detail)."""
    return _load_run(run_id, session)


@router.get("/results/{result_id}", response_model=MatchResultDetail)
def read_result(result_id: uuid.UUID, session: Session = Depends(get_session)) -> LenderMatchResult:
    """One lender's full criterion-by-criterion breakdown, across all of its programs."""
    result = session.scalar(
        select(LenderMatchResult)
        .where(LenderMatchResult.id == result_id)
        .options(selectinload(LenderMatchResult.criteria))
    )
    if result is None:
        fail(404, "Match result not found.")
    return result
