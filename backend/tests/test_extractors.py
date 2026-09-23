"""Provider selection and the request each live extractor sends.

Neither provider is called for real here: a fake client records the request and returns the
recorded Stearns policy. That pins the wire shape (PDF as a document / input_file, the shared
prompt, the strict schema) so a key-holder's first live call is not the first time it runs.
"""

from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from app.config import get_settings
from app.services import extraction
from app.services.extraction import (
    SYSTEM_PROMPT,
    ClaudePolicyExtractor,
    ExtractedPolicy,
    ExtractionError,
    OpenAIPolicyExtractor,
    get_extractor,
)

FIXTURE = Path(__file__).parent / "fixtures" / "extractions" / "EF Credit Box 4.14.2025.json"
PDF = b"%PDF-1.4 fake"


@pytest.fixture
def env(monkeypatch: pytest.MonkeyPatch) -> Iterator[pytest.MonkeyPatch]:
    for key in ("ANTHROPIC_API_KEY", "OPENAI_API_KEY"):
        monkeypatch.setenv(key, "")
    monkeypatch.setenv("EXTRACTION_PROVIDER", "auto")
    get_settings.cache_clear()
    try:
        yield monkeypatch
    finally:
        get_settings.cache_clear()


def _set(monkeypatch: pytest.MonkeyPatch, **values: str) -> None:
    for key, value in values.items():
        monkeypatch.setenv(key, value)
    get_settings.cache_clear()


# --- selection -------------------------------------------------------------------------------


def test_auto_prefers_anthropic_then_openai(env: pytest.MonkeyPatch) -> None:
    _set(env, ANTHROPIC_API_KEY="a", OPENAI_API_KEY="o")
    assert isinstance(get_extractor(), ClaudePolicyExtractor)
    _set(env, ANTHROPIC_API_KEY="")
    assert isinstance(get_extractor(), OpenAIPolicyExtractor)
    _set(env, OPENAI_API_KEY="")
    with pytest.raises(ExtractionError, match="No model is connected for PDF parsing"):
        get_extractor()


def test_explicit_provider_is_honoured_and_checked(env: pytest.MonkeyPatch) -> None:
    _set(env, EXTRACTION_PROVIDER="openai", ANTHROPIC_API_KEY="a", OPENAI_API_KEY="o")
    assert isinstance(get_extractor(), OpenAIPolicyExtractor)
    _set(env, OPENAI_API_KEY="")
    with pytest.raises(ExtractionError, match="OPENAI_API_KEY is not set"):
        get_extractor()
    _set(env, EXTRACTION_PROVIDER="anthropic", ANTHROPIC_API_KEY="")
    with pytest.raises(ExtractionError, match="ANTHROPIC_API_KEY is not set"):
        get_extractor()
    _set(env, EXTRACTION_PROVIDER="bard")
    with pytest.raises(ExtractionError, match="Unknown EXTRACTION_PROVIDER"):
        get_extractor()


# --- request shape ------------------------------------------------------------------------


class _Recorder:
    """Stands in for one SDK method; captures kwargs and returns a canned response."""

    def __init__(self, response: Any) -> None:
        self.calls: list[dict[str, Any]] = []
        self.response = response

    def __call__(self, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        return self.response


def _policy() -> ExtractedPolicy:
    return ExtractedPolicy.model_validate_json(FIXTURE.read_text())


def test_claude_request_sends_pdf_document_and_schema(env: pytest.MonkeyPatch) -> None:
    _set(env, ANTHROPIC_API_KEY="a", EXTRACTION_MODEL="claude-test")
    extractor = ClaudePolicyExtractor()
    recorder = _Recorder(type("R", (), {"stop_reason": "end_turn", "parsed_output": _policy()})())
    extractor.client.messages.parse = recorder  # type: ignore[method-assign]

    result = extractor.extract(PDF, "", "stearns.pdf")

    assert result.lender_name == "Stearns Bank"
    call = recorder.calls[0]
    assert call["model"] == "claude-test" and call["system"] == SYSTEM_PROMPT
    assert call["output_format"] is ExtractedPolicy
    document, text = call["messages"][0]["content"]
    assert document["type"] == "document"
    assert document["source"]["media_type"] == "application/pdf"
    assert document["title"] == "stearns.pdf"
    assert "Extract the complete credit policy" in text["text"]


def test_claude_refusal_and_truncation_become_extraction_errors(env: pytest.MonkeyPatch) -> None:
    _set(env, ANTHROPIC_API_KEY="a")
    extractor = ClaudePolicyExtractor()
    for reason, message in (("refusal", "declined"), ("max_tokens", "too long")):
        extractor.client.messages.parse = _Recorder(  # type: ignore[method-assign]
            type("R", (), {"stop_reason": reason, "parsed_output": None})()
        )
        with pytest.raises(ExtractionError, match=message):
            extractor.extract(PDF, "", "x.pdf")


def test_openai_request_sends_input_file_and_schema(env: pytest.MonkeyPatch) -> None:
    _set(env, OPENAI_API_KEY="o", OPENAI_EXTRACTION_MODEL="gpt-test")
    extractor = OpenAIPolicyExtractor()
    recorder = _Recorder(type("R", (), {"output_parsed": _policy()})())
    extractor.client.responses.parse = recorder  # type: ignore[method-assign]

    result = extractor.extract(PDF, "", "stearns.pdf")

    assert result.lender_name == "Stearns Bank"
    call = recorder.calls[0]
    assert call["model"] == "gpt-test" and call["instructions"] == SYSTEM_PROMPT
    assert call["text_format"] is ExtractedPolicy
    file_part, text_part = call["input"][0]["content"]
    assert file_part["type"] == "input_file" and file_part["filename"] == "stearns.pdf"
    assert file_part["file_data"].startswith("data:application/pdf;base64,")
    assert text_part["type"] == "input_text"


def test_openai_empty_parse_is_an_extraction_error(env: pytest.MonkeyPatch) -> None:
    _set(env, OPENAI_API_KEY="o")
    extractor = OpenAIPolicyExtractor()
    extractor.client.responses.parse = _Recorder(  # type: ignore[method-assign]
        type("R", (), {"output_parsed": None})()
    )
    with pytest.raises(ExtractionError, match="no structured policy"):
        extractor.extract(PDF, "", "x.pdf")


def test_both_providers_share_one_prompt_and_schema() -> None:
    # The downstream pipeline (validation, draft, checklist) never knows which provider ran.
    assert extraction.user_instruction("a.pdf") == extraction.user_instruction("a.pdf")
    for cls in (ClaudePolicyExtractor, OpenAIPolicyExtractor):
        assert cls.extract.__annotations__["return"] == "ExtractedPolicy"
