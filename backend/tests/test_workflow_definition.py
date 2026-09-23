"""The Hatchet workflow's shape is checked offline: a structurally valid dummy token lets the
client construct and the workflows register without a server. Behaviour is covered by the
API tests, because the tasks only wrap the same step functions the in-process runner uses."""

import base64
import importlib
import json
from collections.abc import Iterator
from types import ModuleType

import pytest


def _dummy_token() -> str:
    def part(data: dict[str, object]) -> str:
        return base64.urlsafe_b64encode(json.dumps(data).encode()).rstrip(b"=").decode()

    claims = {
        "sub": "707d0855-80ab-4e1f-a156-f1c4546cbf52",
        "server_url": "http://localhost:8888",
        "grpc_broadcast_address": "localhost:7077",
        "exp": 4102444800,
    }
    return ".".join([part({"alg": "ES256", "typ": "JWT"}), part(claims), "c2ln"])


@pytest.fixture
def workflows(monkeypatch: pytest.MonkeyPatch) -> Iterator[ModuleType]:
    from app.config import get_settings
    from app.workflows import client

    monkeypatch.setenv("HATCHET_CLIENT_TOKEN", _dummy_token())
    monkeypatch.setenv("HATCHET_CLIENT_TLS_STRATEGY", "none")
    get_settings.cache_clear()
    client.get_hatchet.cache_clear()
    try:
        yield importlib.import_module("app.workflows.underwriting")
    finally:
        get_settings.cache_clear()
        client.get_hatchet.cache_clear()


def test_run_is_a_three_stage_dag_with_a_failure_handler(workflows: ModuleType) -> None:
    tasks = {task.name: task for task in workflows.underwriting_workflow.tasks}
    assert set(tasks) == {"prepare", "evaluate_lenders", "persist", "on_failure-on-failure"}
    assert [p.name for p in tasks["evaluate_lenders"].parents] == ["prepare"]
    assert [p.name for p in tasks["persist"].parents] == ["evaluate_lenders"]


def test_database_tasks_retry_with_backoff(workflows: ModuleType) -> None:
    run_tasks = {task.name: task for task in workflows.underwriting_workflow.tasks}
    child_tasks = {task.name: task for task in workflows.evaluate_lender_workflow.tasks}
    for task in (run_tasks["prepare"], run_tasks["persist"], child_tasks["evaluate"]):
        assert task.retries == 3
        assert task.backoff_factor == 2.0
        assert task.backoff_max_seconds == 30
    # The fan-out task only orchestrates; its children carry the retries.
    assert run_tasks["evaluate_lenders"].retries == 0


def test_lenders_are_evaluated_by_a_separate_child_workflow(workflows: ModuleType) -> None:
    child = workflows.evaluate_lender_workflow
    assert child.name.endswith("evaluate-lender")
    assert [task.name for task in child.tasks] == ["evaluate"]
    assert set(workflows.LenderInput.model_fields) == {
        "run_id", "policy_version_id", "lender_name", "features",
    }  # fmt: skip


def test_client_refuses_to_start_without_a_token(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.config import get_settings
    from app.workflows import client

    monkeypatch.setenv("HATCHET_CLIENT_TOKEN", "")
    get_settings.cache_clear()
    client.get_hatchet.cache_clear()
    try:
        with pytest.raises(RuntimeError, match="HATCHET_CLIENT_TOKEN is not set"):
            client.get_hatchet()
    finally:
        get_settings.cache_clear()
        client.get_hatchet.cache_clear()


def test_ingestion_workflow_retries_the_model_call_hardest(workflows: ModuleType) -> None:
    ingestion = importlib.import_module("app.workflows.ingestion")
    tasks = {task.name: task for task in ingestion.ingestion_workflow.tasks}
    assert set(tasks) == {"prepare", "extract", "draft", "on_failure-on-failure"}
    assert [p.name for p in tasks["extract"].parents] == ["prepare"]
    assert [p.name for p in tasks["draft"].parents] == ["extract"]
    # The model call gets the most retries and the longest backoff: rate limits are expected.
    assert tasks["extract"].retries == 5 and tasks["extract"].backoff_max_seconds == 60
    assert tasks["prepare"].retries == 3 and tasks["draft"].retries == 3
