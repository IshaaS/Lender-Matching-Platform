"""Underwriting as a Hatchet workflow.

    underwriting
      prepare            validate completeness + derive features          retries, backoff
        -> evaluate_lenders   fan out: one `evaluate-lender` child run per published policy,
                              all in parallel; a child that exhausts its retries becomes an
                              "error" result instead of failing the run
             -> persist       rank + write results in one transaction     retries, idempotent
      on failure         mark the run failed with the task errors

    evaluate-lender (child)
      evaluate           load one policy version and run the engine       retries, backoff

Every task is a thin wrapper over app.services.underwriting, the same functions the in-process
runner uses, so both paths produce identical results.
"""

import uuid
from datetime import timedelta
from typing import Any

from hatchet_sdk import Context
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.db import SessionLocal
from app.engine.evaluator import LenderEvaluation
from app.models import PolicyVersion, Program
from app.services import underwriting as steps
from app.workflows.client import get_hatchet

hatchet = get_hatchet()


class UnderwritingInput(BaseModel):
    run_id: str


class LenderInput(BaseModel):
    run_id: str
    policy_version_id: str
    lender_name: str
    features: dict[str, Any]


underwriting_workflow = hatchet.workflow(name="underwriting", input_validator=UnderwritingInput)
evaluate_lender_workflow = hatchet.workflow(name="evaluate-lender", input_validator=LenderInput)

# Transient database/network trouble is retried with exponential backoff: 2s, 4s, 8s (max 30s).
RETRIES = 3
BACKOFF_FACTOR = 2.0
BACKOFF_MAX_SECONDS = 30


def _load_version(session: Any, version_id: str) -> PolicyVersion:
    version = session.scalar(
        select(PolicyVersion)
        .where(PolicyVersion.id == uuid.UUID(version_id))
        .options(
            selectinload(PolicyVersion.lender),
            selectinload(PolicyVersion.rules),
            selectinload(PolicyVersion.programs).selectinload(Program.rules),
        )
    )
    if version is None:
        raise LookupError(f"Policy version {version_id} not found")
    return version  # type: ignore[no-any-return]


# --- child: one lender ----------------------------------------------------------------------


@evaluate_lender_workflow.task(
    execution_timeout=timedelta(seconds=60),
    retries=RETRIES,
    backoff_factor=BACKOFF_FACTOR,
    backoff_max_seconds=BACKOFF_MAX_SECONDS,
)
def evaluate(input: LenderInput, ctx: Context) -> dict[str, Any]:
    ctx.log(f"Evaluating {input.lender_name} (attempt {ctx.retry_count + 1})")
    with SessionLocal() as session:
        version = _load_version(session, input.policy_version_id)
        evaluation = steps.evaluate_version(version, input.features)
    return {"policy_version_id": input.policy_version_id, "evaluation": evaluation.model_dump()}


# --- parent: the run -----------------------------------------------------------------------


@underwriting_workflow.task(
    execution_timeout=timedelta(seconds=60),
    retries=RETRIES,
    backoff_factor=BACKOFF_FACTOR,
    backoff_max_seconds=BACKOFF_MAX_SECONDS,
)
def prepare(input: UnderwritingInput, ctx: Context) -> dict[str, Any]:
    with SessionLocal() as session:
        _, application = steps.mark_running(session, uuid.UUID(input.run_id))
        # An incomplete application is a permanent failure; retrying cannot fix it, but the
        # retries are cheap and the on-failure task reports the missing fields either way.
        features = steps.build_features(application)
        versions = [
            {"policy_version_id": str(v.id), "lender_name": v.lender.name}
            for v in steps.published_versions(session)
        ]
    ctx.log(f"Derived {len(features)} features; {len(versions)} lenders to evaluate")
    return {"features": features, "versions": versions}


@underwriting_workflow.task(parents=[prepare], execution_timeout=timedelta(minutes=5))
async def evaluate_lenders(input: UnderwritingInput, ctx: Context) -> dict[str, Any]:
    prepared = ctx.task_output(prepare)
    versions: list[dict[str, str]] = prepared["versions"]
    results = await evaluate_lender_workflow.aio_run_many(
        [
            evaluate_lender_workflow.create_bulk_run_item(
                input=LenderInput(run_id=input.run_id, features=prepared["features"], **version),
                key=version["policy_version_id"],
            )
            for version in versions
        ],
        # A lender whose child run fails after all retries must not fail the whole run.
        return_exceptions=True,
    )
    outcomes = []
    for version, result in zip(versions, results, strict=True):
        if isinstance(result, BaseException):
            ctx.log(f"{version['lender_name']} could not be evaluated: {result}")
            outcomes.append({**version, "error": f"{type(result).__name__}: {result}"})
        else:
            outcomes.append({**version, "evaluation": result["evaluate"]["evaluation"]})
    return {"outcomes": outcomes}


@underwriting_workflow.task(
    parents=[evaluate_lenders],
    execution_timeout=timedelta(seconds=90),
    retries=RETRIES,
    backoff_factor=BACKOFF_FACTOR,
    backoff_max_seconds=BACKOFF_MAX_SECONDS,
)
def persist(input: UnderwritingInput, ctx: Context) -> dict[str, Any]:
    features = ctx.task_output(prepare)["features"]
    outcomes = ctx.task_output(evaluate_lenders)["outcomes"]
    with SessionLocal() as session:
        rows = []
        for outcome in outcomes:
            version = _load_version(session, outcome["policy_version_id"])
            if "error" in outcome:
                rows.append(steps.error_row(version, RuntimeError(outcome["error"])))
            else:
                evaluation = LenderEvaluation.model_validate(outcome["evaluation"])
                rows.append(steps.result_row(version, evaluation))
        steps.complete_run(session, uuid.UUID(input.run_id), features, rows)
    eligible = sum(1 for row in rows if row.eligible)
    ctx.log(f"Persisted {len(rows)} results; {eligible} eligible")
    return {"lenders": len(rows), "eligible": eligible}


@underwriting_workflow.on_failure_task()
def on_failure(input: UnderwritingInput, ctx: Context) -> dict[str, str]:
    errors = "; ".join(f"{task}: {error}" for task, error in ctx.task_run_errors.items())
    steps.fail_run(uuid.UUID(input.run_id), errors or "The underwriting workflow failed.")
    return {"status": "failed"}
