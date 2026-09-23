"""Hatchet worker: `python -m app.workflows.worker` (or `make worker`)."""

from app.workflows.client import get_hatchet
from app.workflows.ingestion import ingestion_workflow
from app.workflows.underwriting import evaluate_lender_workflow, underwriting_workflow


def main() -> None:
    worker = get_hatchet().worker(
        "lender-matching-worker",
        # Enough slots for one run's lender fan-out to execute fully in parallel.
        slots=20,
        workflows=[underwriting_workflow, evaluate_lender_workflow, ingestion_workflow],
    )
    worker.start()


if __name__ == "__main__":
    main()
