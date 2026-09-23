"""End-to-end API tests against the configured Postgres. Each test removes what it creates."""

from typing import Any

import pytest

from tests.conftest import Api, requires_db

pytestmark = [requires_db, pytest.mark.integration]

FICO_RULE = {"label": "Minimum FICO", "category": "credit", "field": "fico_score",
             "operator": "gte", "value": 700}  # fmt: skip


def message(response: Any) -> str:
    return str(response.json()["detail"]["message"])


# --- reference data ---------------------------------------------------------------------------


def test_health_catalog_and_samples(api: Api) -> None:
    assert api.client.get("/api/health").json()["database"] == "ok"

    catalog = api.client.get("/api/catalog").json()
    fico = next(f for f in catalog["fields"] if f["key"] == "fico_score")
    assert fico["type"] == "number" and "gte" in fico["operators"] and "in" not in fico["operators"]
    state = next(f for f in catalog["fields"] if f["key"] == "business_state")
    assert "TX" in state["options"] and state["operators"] == ["eq", "neq", "in", "not_in"]

    samples = api.client.get("/api/samples").json()
    assert [s["key"] for s in samples] == ["strong", "marginal", "trucking", "startup"]


# --- applications -----------------------------------------------------------------------------


def test_draft_lifecycle_and_completeness(api: Api) -> None:
    draft = api.create_application({"business": {"legal_name": "pytest partial"}})
    assert draft["status"] == "draft"
    missing = {m["path"] for m in draft["missing_fields"]}
    assert {"business.state", "loan.amount", "guarantors", "equipment"} <= missing

    url = f"/api/applications/{draft['id']}"
    rejected = api.client.post(f"{url}/submit")
    assert rejected.status_code == 422
    assert "required field(s) are missing" in message(rejected)
    assert {"path": "loan.amount", "label": "Requested amount"} in rejected.json()["detail"][
        "errors"
    ]

    completed = api.client.put(url, json=api.sample("strong"))
    assert completed.status_code == 200 and completed.json()["missing_fields"] == []
    assert api.client.post(f"{url}/submit").json()["status"] == "submitted"

    # Submitted applications are immutable.
    assert api.client.put(url, json=api.sample("strong")).status_code == 409
    assert api.client.delete(url).status_code == 409


def test_conditional_requirements(api: Api) -> None:
    trucking = api.create_application(api.sample("trucking", **{"business.trucks_operated": None}))
    assert {"path": "business.trucks_operated", "label": "Trucks operated"} in trucking[
        "missing_fields"
    ]
    corp = api.create_application(
        api.sample("strong", **{"loan.corp_only": True, "guarantors": []})
    )
    assert corp["missing_fields"] == []  # corp-only needs no guarantor


def test_validation_and_not_found(api: Api) -> None:
    bad = api.client.post(
        "/api/applications",
        json={"business": {"state": "ZZ"}, "guarantors": [{"fico_score": 900}]},
    )
    assert bad.status_code == 422
    paths = {e["path"] for e in bad.json()["detail"]["errors"]}
    assert paths == {"business.state", "guarantors.0.fico_score"}

    missing = api.client.get("/api/applications/00000000-0000-0000-0000-000000000000")
    assert missing.status_code == 404 and message(missing) == "Application not found."


def test_duplicate_and_delete(api: Api) -> None:
    original = api.create_application(api.sample("marginal"))
    copy = api.client.post(f"/api/applications/{original['id']}/duplicate")
    assert copy.status_code == 201
    body = copy.json()
    api.application_ids.append(body["id"])
    assert body["id"] != original["id"] and body["status"] == "draft"
    assert body["business"]["legal_name"].endswith("(copy)")
    assert body["guarantors"][0]["fico_score"] == 685

    assert api.client.delete(f"/api/applications/{body['id']}").status_code == 204
    assert api.client.get(f"/api/applications/{body['id']}").status_code == 404


# --- underwriting -----------------------------------------------------------------------------


def test_underwriting_run_end_to_end(api: Api) -> None:
    application = api.create_application(api.sample("strong"))
    api.client.post(f"/api/applications/{application['id']}/submit")
    started = api.client.post(f"/api/applications/{application['id']}/runs")
    assert started.status_code == 202
    run = api.client.get(f"/api/runs/{started.json()['id']}").json()

    assert run["status"] == "completed" and run["error"] is None
    assert run["feature_snapshot"]["comparable_credit_pct"] == 100.0
    seeded = [r for r in run["results"] if not r["lender_name"].startswith("Pytest")]
    assert [r["rank"] for r in run["results"]] == list(range(1, len(run["results"]) + 1))
    by_lender = {r["lender_name"]: r for r in seeded}
    assert by_lender["Apex Commercial Capital"]["matched_program_name"] == "A+ Rate"
    assert by_lender["Apex Commercial Capital"]["program_details"]["rates"]
    advantage = by_lender["Advantage+ Financing"]
    assert not advantage["eligible"] and advantage["fit_score"] == 0
    assert advantage["rejection_reasons"] == [
        "Requested amount is $120,000, outside the accepted range of $10,000 – $75,000."
    ]
    # Eligible lenders rank above ineligible ones, best score first.
    eligible_scores = [r["fit_score"] for r in seeded if r["eligible"]]
    assert eligible_scores == sorted(eligible_scores, reverse=True)
    assert seeded[-1]["lender_name"] == "Advantage+ Financing"

    detail = api.client.get(f"/api/results/{by_lender['Apex Commercial Capital']['id']}").json()
    fico = next(
        c for c in detail["criteria"]
        if c["program_name"] == "A+ Rate" and c["field_key"] == "fico_score"
    )  # fmt: skip
    assert (fico["outcome"], fico["expected"], fico["actual"]) == ("passed", 720, 760)
    assert fico["message"] == "FICO score is 760 (minimum 720)."
    # any_of: satisfied via one alternative (industry) even though the equipment alternative
    # also qualifies - the engine reports which one it credited.
    eligible_via = next(
        c for c in detail["criteria"]
        if c["program_name"] == "A+ Rate" and c["field_key"] is None
    )  # fmt: skip
    assert eligible_via["outcome"] == "passed"
    assert "satisfied by an A+ eligible industry" in eligible_via["message"]
    medical_a = next(p for p in detail["program_summaries"] if p["name"] == "Medical A Rate")
    assert medical_a["applicable"] is False

    refreshed = api.client.get(f"/api/applications/{application['id']}").json()
    assert refreshed["status"] == "completed"
    # 4 lenders are seeded (Stearns is onboarded live, not pre-seeded); Advantage+ is the one
    # ineligible one for this sample.
    assert refreshed["latest_run"]["eligible_count"] >= 3
    listed = api.client.get("/api/applications", params={"status": "completed"}).json()
    assert any(a["id"] == application["id"] and a["latest_run"] for a in listed)
    history = api.client.get(f"/api/applications/{application['id']}/runs").json()
    assert len(history) == 1


def test_run_rejects_incomplete_application(api: Api) -> None:
    draft = api.create_application({"business": {"legal_name": "pytest incomplete"}})
    response = api.client.post(f"/api/applications/{draft['id']}/runs")
    assert response.status_code == 409
    submit_response = api.client.post(f"/api/applications/{draft['id']}/submit")
    assert submit_response.status_code == 422 and submit_response.json()["detail"]["errors"]


# --- lender policies ----------------------------------------------------------------------------


def test_seeded_lenders_are_listed(api: Api) -> None:
    # Of the 5 provided lenders, only 4 are pre-seeded by `make seed`; Stearns Bank is meant to
    # be onboarded live from its PDF instead (see test_upload_produces_a_reviewable_draft), so
    # it is not asserted here one way or the other - it may or may not exist depending on
    # whether that flow has been run against this database.
    lenders = {x["name"]: x for x in api.client.get("/api/lenders").json()}
    apex = lenders["Apex Commercial Capital"]
    assert apex["program_count"] == 7 and apex["published_version"]["status"] == "published"
    version = api.client.get(f"/api/policy-versions/{apex['published_version']['id']}").json()
    assert version["validation_errors"] == []
    tier1 = version["programs"][0]
    assert tier1["name"] == "A+ Rate"
    assert "FICO score at least 720" in [r["summary"] for r in tier1["rules"]]
    assert tier1["applies_when_summary"] == ["No personal guarantor (corp only) is no"]


def test_policy_lifecycle_changes_underwriting_outcome(api: Api) -> None:
    lender = api.create_lender()
    draft_id = lender["draft_version"]["id"]
    versions = f"/api/policy-versions/{draft_id}"

    empty = api.client.post(f"{versions}/publish")
    assert empty.status_code == 409 and "at least one program" in message(empty)

    program = api.client.post(f"{versions}/programs", json={"name": "Standard", "rank": 1})
    assert program.status_code == 201
    program_id = program.json()["id"]

    invalid = api.client.post(
        f"{versions}/rules", json={**FICO_RULE, "program_id": program_id, "operator": "in"}
    )
    assert invalid.status_code == 422 and "cannot be used on number field" in str(invalid.json())

    rule = api.client.post(f"{versions}/rules", json={**FICO_RULE, "program_id": program_id})
    assert rule.status_code == 201 and rule.json()["summary"] == "FICO score at least 700"
    restriction = api.client.post(
        f"{versions}/rules",
        json={"label": "Excluded states", "category": "geography", "field": "business_state",
              "operator": "not_in", "value": ["CA"]},
    )  # fmt: skip
    assert restriction.status_code == 201 and restriction.json()["program_id"] is None

    published = api.client.post(f"{versions}/publish")
    assert published.status_code == 200 and published.json()["status"] == "published"

    # Published versions are frozen.
    frozen = api.client.put(f"/api/rules/{rule.json()['id']}", json={**FICO_RULE, "value": 800})
    assert frozen.status_code == 409 and "only drafts can be edited" in message(frozen)

    def underwrite() -> dict[str, Any]:
        application = api.create_application(api.sample("strong"))
        api.client.post(f"/api/applications/{application['id']}/submit")
        run_id = api.client.post(f"/api/applications/{application['id']}/runs").json()["id"]
        results = api.client.get(f"/api/runs/{run_id}").json()["results"]
        return next(r for r in results if r["lender_id"] == lender["id"])

    before = underwrite()
    assert before["eligible"] and before["policy_version_number"] == 1

    # Editing = draft (clone) -> change -> publish. FICO 760 no longer clears an 800 minimum.
    draft = api.client.post(f"/api/lenders/{lender['id']}/draft").json()
    assert draft["version_number"] == 2 and draft["status"] == "draft"
    assert len(draft["rules"]) == 1 and len(draft["programs"][0]["rules"]) == 1
    cloned_rule = draft["programs"][0]["rules"][0]
    assert cloned_rule["id"] != rule.json()["id"]
    changed = api.client.put(f"/api/rules/{cloned_rule['id']}", json={**FICO_RULE, "value": 800})
    assert changed.status_code == 200 and changed.json()["value"] == 800
    assert api.client.post(f"/api/policy-versions/{draft['id']}/publish").status_code == 200

    after = underwrite()
    assert not after["eligible"] and after["policy_version_number"] == 2
    assert after["rejection_reasons"] == ["Standard: FICO score is 760, below the minimum of 800."]

    history = api.client.get(f"/api/lenders/{lender['id']}/versions").json()
    assert [(v["version_number"], v["status"]) for v in history] == [
        (2, "published"),
        (1, "archived"),
    ]
    # Lenders with results cannot be deleted, only deactivated.
    assert api.client.delete(f"/api/lenders/{lender['id']}").status_code == 409
    off = api.client.patch(f"/api/lenders/{lender['id']}", json={"is_active": False})
    assert off.json()["is_active"] is False
