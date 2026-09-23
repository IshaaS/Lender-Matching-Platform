import uuid
from typing import Any

from fastapi import APIRouter, Depends, Response
from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.api.errors import fail
from app.db import get_session
from app.engine.policy import Condition, Rule
from app.models import IngestionJob, Lender, LenderMatchResult, PolicyRule, PolicyVersion, Program
from app.models.enums import PolicyStatus
from app.schemas.ingestion import ExtractionReview
from app.schemas.policy import (
    LenderIn,
    LenderOut,
    LenderPatch,
    PolicyVersionOut,
    PolicyVersionSummary,
    ProgramIn,
    ProgramOut,
    ProgramPatch,
    RuleIn,
    RuleOut,
)
from app.services import policies
from app.services.policies import PolicyStateError

router = APIRouter(tags=["lender policies"])

_VERSION_LOAD = (
    selectinload(PolicyVersion.lender),
    selectinload(PolicyVersion.rules),
    selectinload(PolicyVersion.programs).selectinload(Program.rules),
)


# --- loaders ------------------------------------------------------------------------------


def _lender(lender_id: uuid.UUID, session: Session) -> Lender:
    lender = session.scalar(
        select(Lender)
        .where(Lender.id == lender_id)
        .options(selectinload(Lender.policy_versions).options(*_VERSION_LOAD[1:]))
    )
    if lender is None:
        fail(404, "Lender not found.")
    return lender


def _version(version_id: uuid.UUID, session: Session) -> PolicyVersion:
    version = session.scalar(
        select(PolicyVersion)
        .where(PolicyVersion.id == version_id)
        .options(*_VERSION_LOAD)
        .execution_options(populate_existing=True)
    )
    if version is None:
        fail(404, "Policy version not found.")
    return version


def _draft(version_id: uuid.UUID, session: Session) -> PolicyVersion:
    version = _version(version_id, session)
    try:
        policies.require_draft(version)
    except PolicyStateError as error:
        fail(409, str(error))
    return version


# --- serialisers ----------------------------------------------------------------------------


def _rule_out(rule: PolicyRule) -> RuleOut:
    return RuleOut(
        id=rule.id, program_id=rule.program_id, kind=rule.kind, label=rule.label,
        category=rule.category, severity=rule.severity, field=rule.field_key,
        operator=rule.operator, value=rule.value, alternatives=rule.alternatives or [],
        applies_when=rule.applies_when or [], message_template=rule.message_template,
        source_document=rule.source_document, source_quote=rule.source_quote,
        source_page=rule.source_page, sort_order=rule.sort_order,
        summary=policies.describe_rule(rule),
    )  # fmt: skip


def _program_out(program: Program) -> ProgramOut:
    return ProgramOut(
        id=program.id, name=program.name, rank=program.rank, decision_mode=program.decision_mode,
        description=program.description, applies_when=program.applies_when or [],
        applies_when_summary=[policies.describe_condition(c) for c in program.applies_when or []],
        details=program.details or {}, rules=[_rule_out(r) for r in program.rules],
    )  # fmt: skip


def _extraction_review(session: Session, version: PolicyVersion) -> ExtractionReview | None:
    job = session.scalar(select(IngestionJob).where(IngestionJob.policy_version_id == version.id))
    if job is None:
        return None
    return ExtractionReview(
        job_id=job.id, filename=job.filename, extractor=job.extractor,
        uncertainties=job.uncertainties or [], completed_at=job.completed_at,
    )  # fmt: skip


def _version_out(version: PolicyVersion, session: Session | None = None) -> PolicyVersionOut:
    return PolicyVersionOut(
        **PolicyVersionSummary.model_validate(version).model_dump(),
        lender_id=version.lender_id,
        lender_name=version.lender.name,
        rules=[_rule_out(r) for r in version.rules if r.program_id is None],
        programs=[_program_out(p) for p in version.programs],
        validation_errors=policies.validation_errors(version),
        extraction=_extraction_review(session, version) if session else None,
    )


def _lender_out(lender: Lender) -> LenderOut:
    published = policies.get_version(lender, PolicyStatus.PUBLISHED)
    draft = policies.get_version(lender, PolicyStatus.DRAFT)
    shown = published or draft
    return LenderOut(
        id=lender.id, name=lender.name, slug=lender.slug, contact_name=lender.contact_name,
        contact_email=lender.contact_email, contact_phone=lender.contact_phone,
        is_active=lender.is_active,
        published_version=PolicyVersionSummary.model_validate(published) if published else None,
        draft_version=PolicyVersionSummary.model_validate(draft) if draft else None,
        program_count=len(shown.programs) if shown else 0,
        rule_count=len(shown.rules) if shown else 0,
        updated_at=max([lender.updated_at, *(v.updated_at for v in lender.policy_versions)]),
    )  # fmt: skip


def _validated_rule(data: RuleIn) -> dict[str, Any]:
    """Runs the engine's own validation so nothing unevaluable can be saved."""
    payload = data.model_dump(exclude={"program_id", "sort_order"})
    try:
        Rule.model_validate(payload)
    except ValidationError as error:
        fail(422, "This rule is not valid.", [e["msg"] for e in error.errors()])
    return payload


def _validated_conditions(conditions: list[Any]) -> list[dict[str, Any]]:
    try:
        return [Condition.model_validate(c.model_dump()).model_dump() for c in conditions]
    except ValidationError as error:
        fail(422, "A condition is not valid.", [e["msg"] for e in error.errors()])


# --- lenders --------------------------------------------------------------------------------


@router.get("/lenders", response_model=list[LenderOut])
def list_lenders(session: Session = Depends(get_session)) -> list[LenderOut]:
    lenders = session.scalars(
        select(Lender)
        .options(selectinload(Lender.policy_versions).options(*_VERSION_LOAD[1:]))
        .order_by(Lender.name)
    )
    return [_lender_out(lender) for lender in lenders]


@router.post("/lenders", response_model=LenderOut, status_code=201)
def create_lender(data: LenderIn, session: Session = Depends(get_session)) -> LenderOut:
    """Creates the lender with an empty draft policy, ready for programs and rules."""
    slug = policies.slugify(data.name)
    if session.scalar(select(Lender).where((Lender.name == data.name) | (Lender.slug == slug))):
        fail(409, f"A lender named '{data.name}' already exists.")
    lender = Lender(**data.model_dump(), slug=slug)
    session.add(lender)
    session.flush()
    policies.create_draft(session, lender)
    session.commit()
    return _lender_out(_lender(lender.id, session))


@router.get("/lenders/{lender_id}", response_model=LenderOut)
def read_lender(lender_id: uuid.UUID, session: Session = Depends(get_session)) -> LenderOut:
    return _lender_out(_lender(lender_id, session))


@router.patch("/lenders/{lender_id}", response_model=LenderOut)
def update_lender(
    lender_id: uuid.UUID, data: LenderPatch, session: Session = Depends(get_session)
) -> LenderOut:
    lender = _lender(lender_id, session)
    for key, value in data.model_dump(exclude_unset=True).items():
        setattr(lender, key, value)
    session.commit()
    return _lender_out(_lender(lender_id, session))


@router.delete("/lenders/{lender_id}", status_code=204)
def delete_lender(lender_id: uuid.UUID, session: Session = Depends(get_session)) -> Response:
    lender = _lender(lender_id, session)
    used = session.scalar(
        select(func.count()).select_from(LenderMatchResult).where(
            LenderMatchResult.lender_id == lender_id
        )
    )  # fmt: skip
    if used:
        fail(409, "This lender has past match results. Deactivate it instead of deleting.")
    session.delete(lender)
    session.commit()
    return Response(status_code=204)


# --- versions -------------------------------------------------------------------------------


@router.get("/lenders/{lender_id}/versions", response_model=list[PolicyVersionSummary])
def list_versions(
    lender_id: uuid.UUID, session: Session = Depends(get_session)
) -> list[PolicyVersion]:
    return list(_lender(lender_id, session).policy_versions)


@router.post("/lenders/{lender_id}/draft", response_model=PolicyVersionOut)
def create_draft(lender_id: uuid.UUID, session: Session = Depends(get_session)) -> Any:
    """Returns the lender's draft, cloning the published version if no draft exists yet."""
    draft = policies.create_draft(session, _lender(lender_id, session))
    session.commit()
    return _version_out(_version(draft.id, session), session)


@router.get("/policy-versions/{version_id}", response_model=PolicyVersionOut)
def read_version(version_id: uuid.UUID, session: Session = Depends(get_session)) -> Any:
    return _version_out(_version(version_id, session), session)


@router.post("/policy-versions/{version_id}/publish", response_model=PolicyVersionOut)
def publish_version(version_id: uuid.UUID, session: Session = Depends(get_session)) -> Any:
    version = _version(version_id, session)
    try:
        policies.publish(session, version)
    except PolicyStateError as error:
        fail(409, str(error))
    session.commit()
    return _version_out(_version(version_id, session), session)


@router.delete("/policy-versions/{version_id}", status_code=204)
def discard_draft(version_id: uuid.UUID, session: Session = Depends(get_session)) -> Response:
    session.delete(_draft(version_id, session))
    session.commit()
    return Response(status_code=204)


# --- programs -------------------------------------------------------------------------------


@router.post("/policy-versions/{version_id}/programs", response_model=ProgramOut, status_code=201)
def add_program(
    version_id: uuid.UUID, data: ProgramIn, session: Session = Depends(get_session)
) -> ProgramOut:
    version = _draft(version_id, session)
    program = Program(
        **data.model_dump(exclude={"applies_when"}),
        applies_when=_validated_conditions(data.applies_when),
    )
    version.programs.append(program)
    session.commit()
    return _program_out(program)


def _program(program_id: uuid.UUID, session: Session) -> Program:
    program = session.get(Program, program_id)
    if program is None:
        fail(404, "Program not found.")
    _draft(program.policy_version_id, session)
    return program


@router.patch("/programs/{program_id}", response_model=ProgramOut)
def update_program(
    program_id: uuid.UUID, data: ProgramPatch, session: Session = Depends(get_session)
) -> ProgramOut:
    program = _program(program_id, session)
    changes = data.model_dump(exclude_unset=True, exclude={"applies_when"})
    if data.applies_when is not None:
        changes["applies_when"] = _validated_conditions(data.applies_when)
    for key, value in changes.items():
        setattr(program, key, value)
    session.commit()
    return _program_out(program)


@router.delete("/programs/{program_id}", status_code=204)
def delete_program(program_id: uuid.UUID, session: Session = Depends(get_session)) -> Response:
    session.delete(_program(program_id, session))
    session.commit()
    return Response(status_code=204)


# --- rules ----------------------------------------------------------------------------------


def _apply_rule(rule: PolicyRule, payload: dict[str, Any]) -> None:
    rule.field_key = payload.pop("field")
    for key, value in payload.items():
        setattr(rule, key, value)


@router.post("/policy-versions/{version_id}/rules", response_model=RuleOut, status_code=201)
def add_rule(
    version_id: uuid.UUID, data: RuleIn, session: Session = Depends(get_session)
) -> RuleOut:
    """`program_id` omitted = lender-wide restriction; otherwise a rule of that program."""
    version = _draft(version_id, session)
    if data.program_id and data.program_id not in {p.id for p in version.programs}:
        fail(422, "That program does not belong to this policy version.")
    siblings = [r for r in version.rules if r.program_id == data.program_id]
    rule = PolicyRule(
        policy_version_id=version.id,
        program_id=data.program_id,
        sort_order=data.sort_order
        if data.sort_order is not None
        else max((r.sort_order for r in siblings), default=-1) + 1,
    )
    _apply_rule(rule, _validated_rule(data))
    session.add(rule)
    session.commit()
    return _rule_out(rule)


def _rule(rule_id: uuid.UUID, session: Session) -> PolicyRule:
    rule = session.get(PolicyRule, rule_id)
    if rule is None:
        fail(404, "Rule not found.")
    _draft(rule.policy_version_id, session)
    return rule


@router.put("/rules/{rule_id}", response_model=RuleOut)
def update_rule(
    rule_id: uuid.UUID, data: RuleIn, session: Session = Depends(get_session)
) -> RuleOut:
    rule = _rule(rule_id, session)
    _apply_rule(rule, _validated_rule(data))
    if data.sort_order is not None:
        rule.sort_order = data.sort_order
    session.commit()
    return _rule_out(rule)


@router.delete("/rules/{rule_id}", status_code=204)
def delete_rule(rule_id: uuid.UUID, session: Session = Depends(get_session)) -> Response:
    session.delete(_rule(rule_id, session))
    session.commit()
    return Response(status_code=204)
