import copy
import uuid
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, text
from sqlalchemy.exc import OperationalError

from app.db import SessionLocal, engine
from app.main import app
from app.models import IngestionJob, Lender, LoanApplication
from app.seeds.samples import SAMPLES


def _database_available() -> bool:
    try:
        with engine.connect() as connection:
            connection.execute(text("select 1"))
        return True
    except OperationalError:
        return False


requires_db = pytest.mark.skipif(
    not _database_available(), reason="DATABASE_URL is not reachable; API tests need Postgres"
)


class Api:
    """TestClient wrapper that remembers what it created so the database is left clean."""

    def __init__(self) -> None:
        self.client = TestClient(app)
        self.application_ids: list[str] = []
        self.lender_ids: list[str] = []
        self.job_ids: list[str] = []

    def sample(self, key: str, **overrides: Any) -> dict[str, Any]:
        source = next(s for s in SAMPLES if s["key"] == key)
        payload = copy.deepcopy({k: v for k, v in source.items() if k not in ("key", "title")})
        payload["business"]["legal_name"] = f"pytest {uuid.uuid4().hex[:8]}"
        for path, value in overrides.items():
            *parents, leaf = path.split(".")
            node: Any = payload
            for part in parents:
                node = node[int(part)] if part.isdigit() else node[part]
            node[leaf] = value
        return payload

    def create_application(self, payload: dict[str, Any]) -> dict[str, Any]:
        response = self.client.post("/api/applications", json=payload)
        assert response.status_code == 201, response.text
        body: dict[str, Any] = response.json()
        self.application_ids.append(body["id"])
        return body

    def create_lender(self) -> dict[str, Any]:
        response = self.client.post(
            "/api/lenders", json={"name": f"Pytest Lender {uuid.uuid4().hex[:8]}"}
        )
        assert response.status_code == 201, response.text
        body: dict[str, Any] = response.json()
        self.lender_ids.append(body["id"])
        return body

    def cleanup(self) -> None:
        with SessionLocal() as session:
            # Applications first: match results reference lenders without ON DELETE CASCADE.
            for application_id in self.application_ids:
                application = session.get(LoanApplication, uuid.UUID(application_id))
                if application:
                    session.delete(application)
            session.flush()
            # Ingestion jobs outlive their lender (FK is SET NULL), so remove them explicitly.
            job_ids = [uuid.UUID(i) for i in self.job_ids]
            for job in session.scalars(select(IngestionJob).where(IngestionJob.id.in_(job_ids))):
                session.delete(job)
            for lender in session.scalars(
                select(Lender).where(Lender.id.in_([uuid.UUID(i) for i in self.lender_ids]))
            ):
                session.delete(lender)
            session.commit()


@pytest.fixture
def api() -> Iterator[Api]:
    helper = Api()
    try:
        yield helper
    finally:
        helper.cleanup()
