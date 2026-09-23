"""Idempotent seeding: `python -m app.seeds`. Existing lenders/samples are left untouched.

Loads 4 of the 5 provided lenders (SEEDED_LENDERS); the 5th, Stearns Bank, is meant to be
onboarded live via Lenders -> Onboard from PDF, demonstrating the extraction pipeline itself
rather than trusting pre-seeded data.
"""

from datetime import UTC, date, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import SessionLocal
from app.engine.policy import Policy
from app.models import Business, Lender, LoanApplication, PolicyVersion
from app.models.enums import PolicyStatus
from app.seeds.policies import SEEDED_LENDERS
from app.seeds.samples import SAMPLES
from app.services.application_mapper import apply_payload
from app.services.policy_mapper import populate_version


def seed_lenders(session: Session) -> list[str]:
    created = []
    for factory in SEEDED_LENDERS:
        seed = factory()
        lender_data, policy = seed["lender"], seed["policy"]
        if session.scalar(select(Lender).where(Lender.slug == lender_data["slug"])):
            continue
        # Fail loudly here rather than at underwriting time.
        Policy.model_validate(
            {"lender_id": lender_data["slug"], "lender_name": lender_data["name"], **policy}
        )
        lender = Lender(**lender_data)
        version = PolicyVersion(
            version_number=1,
            status=PolicyStatus.PUBLISHED,
            published_at=datetime.now(UTC),
            source_document=policy.get("source_document"),
            notes="Seeded from the provided lender guideline PDF.",
        )
        lender.policy_versions.append(version)
        populate_version(version, policy)
        session.add(lender)
        created.append(lender.name)
    return created


def seed_samples(session: Session) -> list[str]:
    created = []
    for sample in SAMPLES:
        name = sample["business"]["legal_name"]
        if session.scalar(select(Business).where(Business.legal_name == name)):
            continue
        payload = {k: v for k, v in sample.items() if k not in ("key", "title")}
        for guarantor in payload["guarantors"]:
            raw = guarantor.get("bankruptcy_discharge_date")
            if isinstance(raw, str):
                guarantor["bankruptcy_discharge_date"] = date.fromisoformat(raw)
        payload["loan"] = {**payload["loan"], "notes": sample["title"]}
        session.add(apply_payload(LoanApplication(), payload))
        created.append(name)
    return created


def main() -> None:
    with SessionLocal() as session:
        lenders = seed_lenders(session)
        samples = seed_samples(session)
        session.commit()
    print(f"Lenders created: {lenders or 'none (already seeded)'}")
    print(f"Sample applications created: {samples or 'none (already seeded)'}")


if __name__ == "__main__":
    main()
