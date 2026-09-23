import uuid

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.api.errors import fail
from app.db import get_session
from app.engine.adapters import application_input_from_payload
from app.engine.features import derive_features
from app.models import LoanApplication, UnderwritingRun
from app.models.enums import ApplicationStatus
from app.schemas.application import (
    ApplicationListItem,
    ApplicationOut,
    ApplicationPayload,
    RunSummary,
    SampleApplication,
)
from app.seeds.samples import SAMPLES
from app.services.application_mapper import apply_payload, to_payload
from app.services.completeness import missing_fields

router = APIRouter(prefix="/applications", tags=["applications"])
samples_router = APIRouter(prefix="/samples", tags=["applications"])

_LOAD = (
    selectinload(LoanApplication.business),
    selectinload(LoanApplication.business_credit),
    selectinload(LoanApplication.guarantors),
    selectinload(LoanApplication.equipment_items),
)


def get_application(application_id: uuid.UUID, session: Session) -> LoanApplication:
    application = session.scalar(
        select(LoanApplication).where(LoanApplication.id == application_id).options(*_LOAD)
    )
    if application is None:
        fail(404, "Application not found.")
    return application


def _latest_runs(session: Session, ids: list[uuid.UUID]) -> dict[uuid.UUID, RunSummary]:
    if not ids:
        return {}
    runs = session.scalars(
        select(UnderwritingRun)
        .where(UnderwritingRun.application_id.in_(ids))
        .options(selectinload(UnderwritingRun.results))
        .order_by(UnderwritingRun.created_at)
    )
    latest: dict[uuid.UUID, RunSummary] = {}
    for run in runs:  # ascending, so the last write per application wins
        best = next((r for r in run.results if r.eligible), None)
        latest[run.application_id] = RunSummary(
            id=run.id, status=run.status, mode=run.mode, error=run.error,
            created_at=run.created_at, completed_at=run.completed_at,
            eligible_count=sum(r.eligible for r in run.results), lender_count=len(run.results),
            best_lender=best.lender_name if best else None,
            best_program=best.matched_program_name if best else None,
            best_score=best.fit_score if best else None,
        )  # fmt: skip
    return latest


def _out(session: Session, application: LoanApplication) -> ApplicationOut:
    payload = to_payload(application)
    latest = _latest_runs(session, [application.id]).get(application.id)
    # The status and the run are read by separate statements, so a run finishing between them
    # would report a completed run on a still-underwriting application. Re-read to stay
    # consistent rather than leaving the client to poll a state that will never change.
    if latest and latest.status in ("completed", "failed"):
        session.refresh(application, ["status"])
    return ApplicationOut(
        **payload,
        id=application.id,
        status=application.status,
        created_at=application.created_at,
        updated_at=application.updated_at,
        missing_fields=missing_fields(payload),
        latest_run=latest,
    )


def _require_draft(application: LoanApplication) -> None:
    if application.status != ApplicationStatus.DRAFT:
        fail(
            409,
            f"This application is {application.status} and can no longer be changed. "
            "Duplicate it to try different values.",
        )


@router.get("", response_model=list[ApplicationListItem])
def list_applications(
    status: ApplicationStatus | None = Query(default=None),
    session: Session = Depends(get_session),
) -> list[ApplicationListItem]:
    query = (
        select(LoanApplication)
        .options(selectinload(LoanApplication.business))
        .order_by(LoanApplication.created_at.desc())
    )
    if status:
        query = query.where(LoanApplication.status == status)
    # Runs first: a run finishing mid-request then shows a stale run, not a stale status,
    # and the client keeps polling until both agree.
    application_ids = list(session.scalars(select(LoanApplication.id)))
    runs = _latest_runs(session, application_ids)
    applications = list(session.scalars(query))
    return [
        ApplicationListItem(
            id=a.id, status=a.status, legal_name=a.business.legal_name,
            industry=a.business.industry, state=a.business.state,
            amount=float(a.amount) if a.amount is not None else None, notes=a.notes,
            created_at=a.created_at, updated_at=a.updated_at, latest_run=runs.get(a.id),
        )
        for a in applications
    ]  # fmt: skip


@router.post("", response_model=ApplicationOut, status_code=201)
def create_application(
    payload: ApplicationPayload, session: Session = Depends(get_session)
) -> ApplicationOut:
    application = apply_payload(LoanApplication(), payload.model_dump())
    session.add(application)
    session.commit()
    return _out(session, get_application(application.id, session))


@router.get("/{application_id}", response_model=ApplicationOut)
def read_application(
    application_id: uuid.UUID, session: Session = Depends(get_session)
) -> ApplicationOut:
    return _out(session, get_application(application_id, session))


@router.put("/{application_id}", response_model=ApplicationOut)
def update_application(
    application_id: uuid.UUID,
    payload: ApplicationPayload,
    session: Session = Depends(get_session),
) -> ApplicationOut:
    application = get_application(application_id, session)
    _require_draft(application)
    apply_payload(application, payload.model_dump())
    session.commit()
    return _out(session, get_application(application_id, session))


@router.delete("/{application_id}", status_code=204)
def delete_application(
    application_id: uuid.UUID, session: Session = Depends(get_session)
) -> Response:
    application = get_application(application_id, session)
    _require_draft(application)
    # ORM cascades remove the business, guarantors, credit profile, equipment and runs.
    session.delete(application)
    session.commit()
    return Response(status_code=204)


@router.post("/{application_id}/submit", response_model=ApplicationOut)
def submit_application(
    application_id: uuid.UUID, session: Session = Depends(get_session)
) -> ApplicationOut:
    application = get_application(application_id, session)
    _require_draft(application)
    gaps = missing_fields(to_payload(application))
    if gaps:
        fail(422, f"{len(gaps)} required field(s) are missing.", gaps)
    application.status = ApplicationStatus.SUBMITTED
    session.commit()
    return _out(session, application)


@router.post("/{application_id}/duplicate", response_model=ApplicationOut, status_code=201)
def duplicate_application(
    application_id: uuid.UUID, session: Session = Depends(get_session)
) -> ApplicationOut:
    source = get_application(application_id, session)
    payload = to_payload(source)
    payload["business"]["legal_name"] = f"{source.business.legal_name or 'Untitled'} (copy)"
    copy = apply_payload(LoanApplication(), payload)
    session.add(copy)
    session.commit()
    return _out(session, get_application(copy.id, session))


@router.get("/{application_id}/features")
def preview_features(
    application_id: uuid.UUID, session: Session = Depends(get_session)
) -> dict[str, object]:
    """The derived feature set exactly as the matching engine will see it."""
    application = get_application(application_id, session)
    return derive_features(application_input_from_payload(to_payload(application)))


@samples_router.get("", response_model=list[SampleApplication])
def list_samples() -> list[SampleApplication]:
    return [
        SampleApplication(
            key=s["key"],
            title=s["title"],
            payload=ApplicationPayload.model_validate(
                {k: v for k, v in s.items() if k not in ("key", "title")}
            ),
        )
        for s in SAMPLES
    ]
