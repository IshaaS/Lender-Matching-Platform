"""Underwriting pipeline steps: validate -> derive -> evaluate each lender -> rank -> persist.

Each step is a plain function so it can be driven two ways with identical behaviour:
`execute_run` (in-process) and the Hatchet workflow (app.workflows), which calls the same
functions as tasks.
"""

import logging
import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.db import SessionLocal
from app.engine.adapters import application_input_from_payload
from app.engine.evaluator import CriterionOutcome, LenderEvaluation, evaluate_lender
from app.engine.features import FeatureSet, derive_features
from app.models import (
    CriterionResult,
    Lender,
    LenderMatchResult,
    LoanApplication,
    PolicyVersion,
    Program,
    UnderwritingRun,
)
from app.models.enums import ApplicationStatus, MatchStatus, PolicyStatus, RunMode, RunStatus
from app.services.application_mapper import to_payload
from app.services.completeness import missing_fields
from app.services.policy_mapper import to_engine_policy

logger = logging.getLogger(__name__)


class IncompleteApplicationError(Exception):
    def __init__(self, gaps: list[dict[str, str]]) -> None:
        super().__init__("Application is incomplete: " + ", ".join(g["label"] for g in gaps))
        self.gaps = gaps


# --- steps --------------------------------------------------------------------------------


def create_run(session: Session, application: LoanApplication, mode: RunMode) -> UnderwritingRun:
    run = UnderwritingRun(application_id=application.id, status=RunStatus.QUEUED, mode=mode)
    application.status = ApplicationStatus.UNDERWRITING
    session.add(run)
    session.flush()
    return run


def build_features(application: LoanApplication) -> FeatureSet:
    """Steps 1 + 2: completeness validation and feature derivation."""
    payload = to_payload(application)
    gaps = missing_fields(payload)
    if gaps:
        raise IncompleteApplicationError(gaps)
    return derive_features(application_input_from_payload(payload))


def published_versions(session: Session) -> list[PolicyVersion]:
    return list(
        session.scalars(
            select(PolicyVersion)
            .join(Lender)
            .where(PolicyVersion.status == PolicyStatus.PUBLISHED, Lender.is_active.is_(True))
            .options(
                selectinload(PolicyVersion.lender),
                selectinload(PolicyVersion.rules),
                selectinload(PolicyVersion.programs).selectinload(Program.rules),
            )
            .order_by(Lender.name)
        )
    )


def evaluate_version(version: PolicyVersion, features: FeatureSet) -> LenderEvaluation:
    """Step 3, for one lender. Pure apart from reading the already-loaded policy rows."""
    return evaluate_lender(to_engine_policy(version), features)


def _criterion_rows(evaluation: LenderEvaluation) -> list[CriterionResult]:
    def row(c: CriterionOutcome, program: tuple[str, int] | None, order: int) -> CriterionResult:
        return CriterionResult(
            rule_id=uuid.UUID(c.rule_id) if c.rule_id else None,
            program_name=program[0] if program else None,
            program_rank=program[1] if program else None,
            label=c.label,
            category=c.category,
            severity=c.severity,
            outcome=c.outcome,
            field_key=c.field,
            operator=c.operator,
            expected=c.expected,
            actual=c.actual,
            message=c.message,
            sort_order=order,
        )

    rows = [row(c, None, i) for i, c in enumerate(evaluation.restrictions)]
    for program in evaluation.programs:
        rows += [
            row(c, (program.name, program.rank), program.rank * 1000 + i)
            for i, c in enumerate(program.criteria)
        ]
    return rows


def result_row(version: PolicyVersion, evaluation: LenderEvaluation) -> LenderMatchResult:
    matched = next((p for p in evaluation.programs if p.name == evaluation.matched_program), None)
    return LenderMatchResult(
        lender_id=version.lender_id,
        policy_version_id=version.id,
        lender_name=version.lender.name,
        policy_version_number=version.version_number,
        status=MatchStatus.EVALUATED,
        eligible=evaluation.eligible,
        decision=evaluation.decision,
        matched_program_name=evaluation.matched_program,
        fit_score=evaluation.fit_score,
        score_breakdown=(
            evaluation.score_breakdown.model_dump() if evaluation.score_breakdown else {}
        ),
        near_miss_ratio=evaluation.near_miss_ratio,
        rejection_reasons=evaluation.rejection_reasons,
        program_details=matched.details if matched else {},
        program_summaries=[
            {
                "name": p.name,
                "rank": p.rank,
                "decision_mode": p.decision_mode,
                "decision": p.decision,
                "applicable": p.applicable,
                "applicability_note": p.applicability_note,
                "eligible": p.eligible,
                "hard_failures": p.hard_failures,
            }
            for p in evaluation.programs
        ],
        criteria=_criterion_rows(evaluation),
    )


def error_row(version: PolicyVersion, error: Exception) -> LenderMatchResult:
    """One lender failing to evaluate must not sink the whole run."""
    return LenderMatchResult(
        lender_id=version.lender_id,
        policy_version_id=version.id,
        lender_name=version.lender.name,
        policy_version_number=version.version_number,
        status=MatchStatus.ERROR,
        decision="error",
        error=f"{type(error).__name__}: {error}"[:2000],
        rejection_reasons=["This lender's policy could not be evaluated."],
    )


DECISION_RANK = {
    "eligible": 1,
    "manual_review": 2,
    "needs_information": 3,
    "ineligible": 4,
    "error": 5,
}


def rank_rows(rows: list[LenderMatchResult]) -> list[LenderMatchResult]:
    """Step 4: eligible by fit score, then manual review, then needs info, then near misses."""
    ordered = sorted(
        rows,
        key=lambda r: (
            DECISION_RANK.get(r.decision or ("eligible" if r.eligible else "ineligible"), 4),
            -r.fit_score,
            -float(r.near_miss_ratio or 0),
            r.lender_name,
        ),
    )
    for position, row in enumerate(ordered, start=1):
        row.rank = position
    return ordered


# --- run lifecycle (shared by both drivers) ------------------------------------------------------


def mark_running(session: Session, run_id: uuid.UUID) -> tuple[UnderwritingRun, LoanApplication]:
    run = session.get(UnderwritingRun, run_id)
    if run is None:
        raise LookupError(f"Underwriting run {run_id} not found")
    application = session.get(LoanApplication, run.application_id)
    assert application is not None
    run.status = RunStatus.RUNNING
    run.started_at = run.started_at or datetime.now(UTC)  # keep the first start across retries
    session.commit()
    return run, application


def evaluate_all(session: Session, features: FeatureSet) -> list[LenderMatchResult]:
    """Sequential evaluation with per-lender isolation (the in-process equivalent of the
    Hatchet fan-out)."""
    rows = []
    for version in published_versions(session):
        try:
            rows.append(result_row(version, evaluate_version(version, features)))
        except Exception as error:  # noqa: BLE001 - one lender must not sink the run
            logger.exception("Evaluation failed for %s", version.lender.name)
            rows.append(error_row(version, error))
    return rows


def complete_run(
    session: Session, run_id: uuid.UUID, features: FeatureSet, rows: list[LenderMatchResult]
) -> None:
    """Steps 4 + 5 in one transaction. Replaces any earlier rows, so a retry is idempotent."""
    if not rows:
        raise RuntimeError("No lenders with a published policy to evaluate against.")
    run = session.get(UnderwritingRun, run_id)
    assert run is not None
    run.feature_snapshot = dict(features)
    run.results = rank_rows(rows)
    run.status, run.error, run.completed_at = RunStatus.COMPLETED, None, datetime.now(UTC)
    application = session.get(LoanApplication, run.application_id)
    assert application is not None
    application.status = ApplicationStatus.COMPLETED
    session.commit()


def fail_run(run_id: uuid.UUID, error: str) -> None:
    """Records a failure in a fresh session, since the failing one may be unusable."""
    with SessionLocal() as session:
        run = session.get(UnderwritingRun, run_id)
        if run is None:
            return
        run.status, run.error, run.completed_at = RunStatus.FAILED, error[:2000], datetime.now(UTC)
        application = session.get(LoanApplication, run.application_id)
        if application is not None:
            # Back to submitted so the user can fix the cause and run again.
            application.status = ApplicationStatus.SUBMITTED
        session.commit()


# --- in-process driver ----------------------------------------------------------------------


def execute_run(run_id: uuid.UUID) -> None:
    """Runs the whole pipeline in this process. Never raises: failures land on the run row."""
    try:
        with SessionLocal() as session:
            _, application = mark_running(session, run_id)
            features = build_features(application)
            complete_run(session, run_id, features, evaluate_all(session, features))
    except Exception as error:  # noqa: BLE001
        logger.exception("Underwriting run %s failed", run_id)
        fail_run(run_id, str(error))
