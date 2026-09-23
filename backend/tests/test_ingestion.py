"""PDF ingestion, tested without an API key by injecting a RecordedPolicyExtractor in place
of the live one.

The fixture in tests/fixtures/extractions is authored to the live extractor's schema and
deliberately contains one rule the engine cannot evaluate (an invented field), so the
drop-and-report path is covered as well as the happy path.

RecordedPolicyExtractor is test infrastructure only: the running app has no key-less
extraction path (see test_no_extractor_configured_is_a_clear_error), since silently
substituting canned data would defeat the point of demonstrating PDF parsing.
"""

import uuid
from collections.abc import Iterator
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.config import get_settings
from app.services.extraction import (
    SYSTEM_PROMPT,
    ExtractedPolicy,
    ExtractionError,
    RecordedPolicyExtractor,
    build_draft,
    get_extractor,
)
from app.services.ingestion import extract_text
from tests.conftest import Api, requires_db

FIXTURES = Path(__file__).parent / "fixtures" / "extractions"
PDFS = Path(__file__).parents[2] / "docs" / "lender-pdfs"
STEARNS_PDF = PDFS / "EF Credit Box 4.14.2025.pdf"


@pytest.fixture
def recorded(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Iterator[RecordedPolicyExtractor]:
    """Makes app.services.ingestion use a RecordedPolicyExtractor for this test, standing in
    for a live model call without needing a key or network access."""
    extractor = RecordedPolicyExtractor(FIXTURES)
    monkeypatch.setattr("app.services.ingestion.get_extractor", lambda: extractor)
    monkeypatch.setenv("UPLOADS_DIR", str(tmp_path / "uploads"))
    get_settings.cache_clear()
    try:
        yield extractor
    finally:
        get_settings.cache_clear()


# --- extractor + conversion (no database) ---------------------------------------------------


def test_prompt_carries_the_live_catalog() -> None:
    # The model may only use fields and operators the engine knows; both come from the
    # registries at import time, so a new field is usable by the extractor with no prompt edit.
    assert "fico_score | number" in SYSTEM_PROMPT
    assert "equipment_category | enum" in SYSTEM_PROMPT and "class_8_truck" in SYSTEM_PROMPT
    assert "- not_in | is none of | list" in SYSTEM_PROMPT


def test_extraction_schema_is_strict() -> None:
    schema = ExtractedPolicy.model_json_schema()
    # Structured outputs need every property required and no open-ended values.
    assert set(schema["required"]) == set(schema["properties"])
    value_schema = schema["$defs"]["ExtractedValue"]
    assert set(value_schema["required"]) == {"number", "text", "boolean", "options", "range"}
    with pytest.raises(ValidationError):
        ExtractedPolicy.model_validate({"lender_name": "X"})  # missing required lists


def test_recorded_extractor_replays_by_filename() -> None:
    extractor = RecordedPolicyExtractor(FIXTURES)
    policy = extractor.extract(b"%PDF", "", STEARNS_PDF.name)
    assert policy.lender_name == "Stearns Bank"
    assert [p.name for p in policy.programs][:3] == ["Tier 1", "Tier 2", "Tier 3"]
    with pytest.raises(ExtractionError, match="No recorded extraction"):
        extractor.extract(b"%PDF", "", "unknown-lender.pdf")


def test_no_extractor_configured_is_a_clear_error(monkeypatch: pytest.MonkeyPatch) -> None:
    # No key, no recorded replay, even for a PDF that matches one of the seeded lenders by
    # name: the app never falls back to canned data.
    monkeypatch.setenv("ANTHROPIC_API_KEY", "")
    monkeypatch.setenv("OPENAI_API_KEY", "")
    get_settings.cache_clear()
    try:
        with pytest.raises(ExtractionError, match="No model is connected for PDF parsing"):
            get_extractor()
    finally:
        get_settings.cache_clear()


def test_build_draft_keeps_valid_rules_and_reports_the_rest() -> None:
    extracted = RecordedPolicyExtractor(FIXTURES).extract(b"%PDF", "", STEARNS_PDF.name)
    draft = build_draft(extracted)

    labels = [r["label"] for r in draft.policy["rules"]]
    assert "Comparable debt" in labels and "No bankruptcy in last 7 years" in labels
    # The invented field is dropped from the draft and surfaces on the checklist instead.
    assert "Non-essential use equipment" not in labels
    assert len(draft.dropped) == 1
    assert "equipment_is_essential_use" in draft.dropped[0].reason
    assert draft.dropped[0].suggestion

    tier1 = draft.policy["programs"][0]
    assert tier1["applies_when"] == [
        {"field": "corp_only", "operator": "is_false", "value": None, "label": None},
        {"field": "has_paynet", "operator": "is_true", "value": None, "label": None},
    ]
    assert {r["field"]: r["value"] for r in tier1["rules"]} == {
        "fico_score": 725, "years_in_business": 3, "paynet_score": 685,
    }  # fmt: skip


def test_extracted_draft_matches_the_hand_seeded_policy() -> None:
    """The recorded extraction and the hand-modelled seed agree on every Stearns tier."""
    from datetime import date

    from app.engine.adapters import application_input_from_payload
    from app.engine.evaluator import evaluate_lender
    from app.engine.features import derive_features
    from app.engine.policy import Policy
    from app.seeds import policies as seeds
    from app.seeds import samples

    extracted = build_draft(
        RecordedPolicyExtractor(FIXTURES).extract(b"%PDF", "", STEARNS_PDF.name)
    ).policy
    ingested = Policy.model_validate({"lender_id": "i", "lender_name": "Stearns", **extracted})
    seed = seeds.stearns()
    hand = Policy.model_validate({"lender_id": "s", "lender_name": "Stearns", **seed["policy"]})

    for sample in samples.SAMPLES:
        if sample["loan"]["corp_only"]:
            continue  # the recorded extraction flags the corp-only table as unmodelled
        features = derive_features(application_input_from_payload(sample), today=date(2026, 1, 1))
        assert (
            evaluate_lender(ingested, features).matched_program
            == evaluate_lender(hand, features).matched_program
        ), sample["key"]


def test_text_extraction_reads_the_real_pdf() -> None:
    text = extract_text(STEARNS_PDF.read_bytes())
    assert "No BK in last 7 years" in text and "Tier 1" in text


# --- the API, end to end -------------------------------------------------------------------


@requires_db
@pytest.mark.integration
def test_upload_produces_a_reviewable_draft(api: Api, recorded: None) -> None:
    name = f"Pytest Ingested {uuid.uuid4().hex[:8]}"
    with STEARNS_PDF.open("rb") as pdf:
        response = api.client.post(
            "/api/ingestion",
            files={"file": (STEARNS_PDF.name, pdf, "application/pdf")},
            data={"new_lender_name": name},
        )
    assert response.status_code == 202, response.text
    api.job_ids.append(response.json()["id"])
    job = api.client.get(f"/api/ingestion/{response.json()['id']}").json()
    assert job["status"] == "draft_ready", job["error"]
    assert job["extractor"] == "recorded" and job["lender_name"] == name
    api.lender_ids.append(job["lender_id"])

    # Nothing is published: the lender exists with a draft only.
    lender = api.client.get(f"/api/lenders/{job['lender_id']}").json()
    assert lender["published_version"] is None
    assert lender["draft_version"]["id"] == job["policy_version_id"]

    version = api.client.get(f"/api/policy-versions/{job['policy_version_id']}").json()
    assert version["status"] == "draft" and version["validation_errors"] == []
    assert len(version["programs"]) == 6 and len(version["rules"]) == 7
    assert version["source_document"] == STEARNS_PDF.name
    # The reviewer's checklist: the extractor's own notes plus the dropped rule.
    items = [u["item"] for u in version["extraction"]["uncertainties"]]
    assert "Corp-only tier table" in items
    assert any("Non-essential use equipment" in item for item in items)

    # It is an ordinary draft: publishable straight from the editor after review.
    published = api.client.post(f"/api/policy-versions/{version['id']}/publish")
    assert published.status_code == 200 and published.json()["status"] == "published"

    jobs = api.client.get("/api/ingestion").json()
    assert any(j["id"] == job["id"] for j in jobs)


@requires_db
@pytest.mark.integration
def test_upload_rejections(api: Api, recorded: None) -> None:
    not_pdf = api.client.post(
        "/api/ingestion",
        files={"file": ("notes.txt", b"hello", "text/plain")},
        data={"new_lender_name": "x"},
    )
    assert not_pdf.status_code == 422 and "Only PDF" in not_pdf.json()["detail"]["message"]

    with STEARNS_PDF.open("rb") as pdf:
        nobody = api.client.post(
            "/api/ingestion", files={"file": (STEARNS_PDF.name, pdf, "application/pdf")}
        )
    assert nobody.status_code == 422
    assert "Choose an existing lender" in nobody.json()["detail"]["message"]


@requires_db
@pytest.mark.integration
def test_failed_extraction_is_reported_and_retryable(
    api: Api, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # Simulate a transient extractor failure (e.g. the model API erroring): the job fails and
    # records why.
    def _failing_extractor() -> RecordedPolicyExtractor:
        raise ExtractionError("simulated extractor failure")

    monkeypatch.setattr("app.services.ingestion.get_extractor", _failing_extractor)
    monkeypatch.setenv("UPLOADS_DIR", str(tmp_path / "uploads"))
    get_settings.cache_clear()
    try:
        with STEARNS_PDF.open("rb") as pdf:
            response = api.client.post(
                "/api/ingestion",
                files={"file": (STEARNS_PDF.name, pdf, "application/pdf")},
                data={"new_lender_name": f"Pytest Failed {uuid.uuid4().hex[:8]}"},
            )
        api.job_ids.append(response.json()["id"])
        job = api.client.get(f"/api/ingestion/{response.json()['id']}").json()
        assert job["status"] == "failed" and "simulated extractor failure" in job["error"]
        assert job["lender_id"] is None  # no lender is created for a failed extraction

        # A working extractor comes back and the same job is retried: it now succeeds.
        monkeypatch.setattr(
            "app.services.ingestion.get_extractor", lambda: RecordedPolicyExtractor(FIXTURES)
        )
        retried = api.client.post(f"/api/ingestion/{job['id']}/retry")
        assert retried.status_code == 202
        job = api.client.get(f"/api/ingestion/{job['id']}").json()
        assert job["status"] == "draft_ready", job["error"]
        api.lender_ids.append(job["lender_id"])
    finally:
        get_settings.cache_clear()
