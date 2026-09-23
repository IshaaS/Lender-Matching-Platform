"""PDF ingestion as a Hatchet workflow.

    ingestion
      prepare            read the PDF, store its text                   retries, backoff
        -> extract       call the policy extractor (the model)           retries with longer
                                                                         backoff: rate limits and
                                                                         transient API errors
             -> draft    validate + write the draft version              retries, idempotent
      on failure         mark the job failed

Same step functions as app.services.ingestion, so the in-process runner behaves identically.
"""

import uuid
from datetime import timedelta
from typing import Any

from hatchet_sdk import Context
from pydantic import BaseModel

from app.db import SessionLocal
from app.services import ingestion as steps
from app.services.extraction import ExtractedPolicy, get_extractor
from app.workflows.client import get_hatchet

hatchet = get_hatchet()


class IngestionInput(BaseModel):
    job_id: str


ingestion_workflow = hatchet.workflow(name="ingestion", input_validator=IngestionInput)


@ingestion_workflow.task(
    execution_timeout=timedelta(seconds=60), retries=3, backoff_factor=2.0, backoff_max_seconds=30
)
def prepare(input: IngestionInput, ctx: Context) -> dict[str, Any]:
    with SessionLocal() as session:
        job = steps.mark_extracting(session, uuid.UUID(input.job_id))
        ctx.log(f"Read {len(job.extracted_text or '')} characters from {job.filename}")
    return {"ok": True}


@ingestion_workflow.task(
    parents=[prepare],
    # A model call can legitimately take a while on a long document.
    execution_timeout=timedelta(minutes=5),
    # Rate limits and 5xx from the model API are retried: 5s, 10s, 20s, 40s, 60s.
    retries=5,
    backoff_factor=2.0,
    backoff_max_seconds=60,
)
def extract(input: IngestionInput, ctx: Context) -> dict[str, Any]:
    with SessionLocal() as session:
        job = steps.mark_extracting(session, uuid.UUID(input.job_id))
        ctx.log(
            f"Extracting with the {get_extractor().name} extractor (attempt {ctx.retry_count + 1})"
        )
        extracted = steps.extract_policy(job)
    return {"extractor": get_extractor().name, "policy": extracted.model_dump()}


@ingestion_workflow.task(
    parents=[extract],
    execution_timeout=timedelta(seconds=60),
    retries=3,
    backoff_factor=2.0,
    backoff_max_seconds=30,
)
def draft(input: IngestionInput, ctx: Context) -> dict[str, Any]:
    output = ctx.task_output(extract)
    extracted = ExtractedPolicy.model_validate(output["policy"])
    with SessionLocal() as session:
        version = steps.create_draft(
            session, uuid.UUID(input.job_id), extracted, output["extractor"]
        )
        ctx.log(
            f"Draft v{version.version_number}: {len(version.programs)} programs, "
            f"{len(version.rules)} rules, {len(extracted.uncertainties)} items to review"
        )
        return {"policy_version_id": str(version.id)}


@ingestion_workflow.on_failure_task()
def on_failure(input: IngestionInput, ctx: Context) -> dict[str, str]:
    errors = "; ".join(f"{task}: {error}" for task, error in ctx.task_run_errors.items())
    steps.fail_job(uuid.UUID(input.job_id), errors or "The ingestion workflow failed.")
    return {"status": "failed"}
