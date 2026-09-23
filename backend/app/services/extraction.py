"""Turns a lender guideline PDF into a draft policy document.

The extractor is an interface with two implementations:

  ClaudePolicyExtractor    Anthropic: the PDF as a document block + structured outputs
  OpenAIPolicyExtractor    OpenAI: the PDF as an input_file + Responses API structured outputs
  RecordedPolicyExtractor  replays a saved response - test infrastructure only; there is no
                           key-less path in the running app, since that would defeat the point
                           of demonstrating PDF parsing and normalisation

Both live extractors share the prompt and the schema, so swapping providers changes nothing
downstream: the same validation, the same draft, the same review checklist.

Whatever comes back is converted to the same policy dict the seeds use and validated by the
engine's own Policy model before anything is stored, so an unevaluable draft is rejected here.
"""

from __future__ import annotations

import base64
import json
import logging
from pathlib import Path
from typing import Any, Literal, Protocol, Self

from pydantic import BaseModel, Field, ValidationError, model_validator

from app.config import get_settings
from app.engine.catalog import CATEGORIES, FIELDS, FieldType
from app.engine.operators import OPERATORS, ValueShape
from app.engine.policy import Policy

logger = logging.getLogger(__name__)

# --- what the model is asked to produce ---------------------------------------------------------
# Every field is required and there are no open-ended types: structured outputs need a strict
# schema, and a rule value can be a number, a string, a boolean, a list or a range, so each
# shape gets its own slot and exactly one is expected to be filled.


class ExtractedValue(BaseModel):
    number: float | None
    text: str | None
    boolean: bool | None
    options: list[str] | None
    range: list[float] | None

    @model_validator(mode="after")
    def _check_single_slot(self) -> Self:
        non_null_slots = [
            slot for slot in ("number", "text", "boolean", "options", "range")
            if getattr(self, slot) is not None
        ]
        if len(non_null_slots) > 1:
            raise ValueError(
                f"ExtractedValue must have at most one non-null slot, got {non_null_slots}"
            )
        return self

    def resolve(self) -> object:
        for candidate in (self.number, self.text, self.boolean, self.options, self.range):
            if candidate is not None:
                return candidate
        return None


class ExtractedCondition(BaseModel):
    field: str
    operator: str
    value: ExtractedValue
    label: str | None = None


class ExtractedRule(BaseModel):
    kind: Literal["simple", "any_of"]
    label: str
    category: str
    severity: Literal["hard", "soft"]
    field: str | None = None
    operator: str | None = None
    value: ExtractedValue | None = None
    alternatives: list[ExtractedCondition] = Field(default_factory=list)
    applies_when: list[ExtractedCondition] = Field(default_factory=list)
    # Where in the document this came from, so a reviewer can check it quickly.
    source_quote: str | None = None


class ExtractedProgram(BaseModel):
    name: str
    rank: int
    description: str | None
    applies_when: list[ExtractedCondition]
    rules: list[ExtractedRule]
    # Rates, documents, commission caps: display-only, free-form.
    details: list[ExtractedDetail]


class ExtractedDetail(BaseModel):
    key: str
    value: str


class Uncertainty(BaseModel):
    item: str
    reason: str
    suggestion: str | None


class ExtractedPolicy(BaseModel):
    lender_name: str
    contact_name: str | None
    contact_email: str | None
    contact_phone: str | None
    rules: list[ExtractedRule]
    programs: list[ExtractedProgram]
    # Anything in the PDF that could not be expressed with the catalog, or that needed a
    # judgement call. This list is the reviewer's checklist.
    uncertainties: list[Uncertainty]


# --- extractor interface -------------------------------------------------------------------


class ExtractionError(Exception):
    """The document could not be turned into a policy (retryable at the workflow level)."""


class PolicyExtractor(Protocol):
    name: str

    def extract(self, pdf_bytes: bytes, pdf_text: str, filename: str) -> ExtractedPolicy: ...


def catalog_reference() -> str:
    """The field catalog and operator registry, rendered for the prompt. Regenerated on each
    call so a new field on the backend is immediately usable by the extractor."""
    lines = ["FIELDS (key | type | unit | allowed operators | options):"]
    for f in FIELDS:
        options = f"options={list(f.options)}" if f.type is FieldType.ENUM else ""
        ops = [op.key for op in OPERATORS.values() if f.type in op.field_types]
        note = f" - {f.description}" if f.description else ""
        lines.append(f"- {f.key} | {f.type} | {f.unit or '-'} | {ops} {options}{note}")
    lines.append("\nOPERATORS (key | meaning | value shape):")
    for op in OPERATORS.values():
        lines.append(f"- {op.key} | {op.label} | {op.shape}")
    lines.append(f"\nCATEGORIES: {list(CATEGORIES)}")
    return "\n".join(lines)


SYSTEM_PROMPT = """You convert equipment-finance lender guideline documents into structured credit policies for an underwriting engine.

The engine evaluates loan applications against rules. A rule tests ONE catalog field with ONE operator and a value. Rules live either at the lender level (restrictions that apply before any program: excluded states, industries, equipment, transaction types, derogatory-history bans, US-citizen requirements) or inside a program (a tier or credit box with its own FICO / PayNet / time-in-business thresholds and amount limits).

How to model what you read:
- Programs are ranked; rank 1 is the most favourable tier. Give every tier or pricing program in the document its own program, in the order the lender would prefer to place a deal.
- When a document publishes alternative tables (e.g. different thresholds when there is no PayNet score, or for corp-only requests), model each table as its own set of programs with an `applies_when` condition that selects it (has_paynet is_false; corp_only is_true).
- Use `applies_when` on a rule when the document says a requirement only applies in some cases (e.g. bankruptcy seasoning only when has_bankruptcy is_true; a Class 8 age limit only when equipment_category is class_8_truck).
- "Prefer", "typically", "ideal" language is a soft rule (severity "soft"). Everything phrased as a requirement, minimum, maximum or exclusion is hard.
- App-only / documentation ceilings (above which full financials are required) are soft rules, not declines; put the documentation requirement in the program `details`.
- Use kind "any_of" with `alternatives` when the document accepts one of several things.
- Rates, buy rates, points, turnaround times and required documents are display-only: put them in program `details`, never as rules.
- Map the document's own words onto catalog options (e.g. "OTR" -> industry trucking; "CA, NV" -> business_state not_in ["CA","NV"]). If something in the document cannot be expressed with the catalog fields and operators, do NOT invent a field: leave it out and record it in `uncertainties` with a suggestion.
- Record every judgement call in `uncertainties`. A reviewer will read that list before publishing.
- Use ONLY the field keys, operators and enum options listed below. Values must match the field type: numbers for number fields, one of the listed options for enum fields (lists of them for in / not_in), booleans for boolean fields, [min, max] for between.

For each value, fill exactly one slot of the value object (number, text, boolean, options or range) and leave the others null.

""" + catalog_reference()  # noqa: E501


def user_instruction(filename: str) -> str:
    return (
        f"Extract the complete credit policy from '{filename}'. "
        "Cover every tier, restriction and condition in the document."
    )


class ClaudePolicyExtractor:
    name = "claude"

    def __init__(self, model: str | None = None) -> None:
        import anthropic

        settings = get_settings()
        self.model = model or settings.extraction_model
        self.client = anthropic.Anthropic(api_key=settings.anthropic_api_key)

    def extract(self, pdf_bytes: bytes, pdf_text: str, filename: str) -> ExtractedPolicy:
        import anthropic

        try:
            response = self.client.messages.parse(
                model=self.model,
                max_tokens=16000,
                system=SYSTEM_PROMPT,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "document",
                                "source": {
                                    "type": "base64",
                                    "media_type": "application/pdf",
                                    "data": base64.standard_b64encode(pdf_bytes).decode(),
                                },
                                "title": filename,
                            },
                            {"type": "text", "text": user_instruction(filename)},
                        ],
                    }
                ],
                output_format=ExtractedPolicy,
            )
        except anthropic.RateLimitError as error:
            raise ExtractionError(f"Rate limited by the model API: {error.message}") from error
        except anthropic.APIStatusError as error:
            if error.status_code >= 500:
                raise ExtractionError(f"Model API error {error.status_code}") from error
            raise
        except anthropic.APIConnectionError as error:
            raise ExtractionError("Could not reach the model API") from error

        if response.stop_reason == "refusal":
            raise ExtractionError("The model declined to process this document.")
        if response.stop_reason == "max_tokens":
            raise ExtractionError("The document is too long to extract in one pass.")
        if response.parsed_output is None:
            raise ExtractionError("The model returned no structured policy.")
        return response.parsed_output


class OpenAIPolicyExtractor:
    name = "openai"

    def __init__(self, model: str | None = None) -> None:
        import openai

        settings = get_settings()
        self.model = model or settings.openai_extraction_model
        self.client = openai.OpenAI(
            api_key=settings.openai_api_key, base_url=settings.openai_base_url
        )

    def extract(self, pdf_bytes: bytes, pdf_text: str, filename: str) -> ExtractedPolicy:
        import openai

        try:
            response = self.client.responses.parse(
                model=self.model,
                instructions=SYSTEM_PROMPT,
                input=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "input_file",
                                "filename": filename,
                                "file_data": "data:application/pdf;base64,"
                                + base64.standard_b64encode(pdf_bytes).decode(),
                            },
                            {"type": "input_text", "text": user_instruction(filename)},
                        ],
                    }
                ],
                text_format=ExtractedPolicy,
                max_output_tokens=16000,
            )
        except openai.RateLimitError as error:
            raise ExtractionError(f"Rate limited by the model API: {error.message}") from error
        except openai.LengthFinishReasonError as error:
            raise ExtractionError("The document is too long to extract in one pass.") from error
        except openai.ContentFilterFinishReasonError as error:
            raise ExtractionError("The model declined to process this document.") from error
        except openai.APIStatusError as error:
            if error.status_code >= 500:
                raise ExtractionError(f"Model API error {error.status_code}") from error
            raise
        except openai.APIConnectionError as error:
            raise ExtractionError("Could not reach the model API") from error

        if response.output_parsed is None:
            raise ExtractionError("The model returned no structured policy.")
        return response.output_parsed


class RecordedPolicyExtractor:
    """Replays a saved extraction. `source` is a JSON file or a directory of them keyed by
    the uploaded filename's stem. Used only by tests, via `get_extractor` monkeypatched to
    return an instance - it is not selectable through configuration."""

    name = "recorded"

    def __init__(self, source: Path) -> None:
        self.source = source

    def extract(self, pdf_bytes: bytes, pdf_text: str, filename: str) -> ExtractedPolicy:
        path = self.source
        if path.is_dir():
            path = path / f"{Path(filename).stem}.json"
        if not path.exists():
            raise ExtractionError(f"No recorded extraction for '{filename}' at {path}")
        return ExtractedPolicy.model_validate_json(path.read_text())


def get_extractor() -> PolicyExtractor:
    """Picks the live extractor from settings: EXTRACTION_PROVIDER selects `anthropic` or
    `openai`; `auto` (the default) uses whichever provider has a key, preferring Anthropic
    when both do. There is no key-less mode - PDF parsing is the model's job, not a lookup
    table, so without a key onboarding says so rather than quietly faking it.
    """
    settings = get_settings()
    provider = settings.extraction_provider
    if provider == "auto":
        if settings.anthropic_api_key:
            provider = "anthropic"
        elif settings.openai_api_key:
            provider = "openai"
        else:
            raise ExtractionError(
                "No model is connected for PDF parsing. Set ANTHROPIC_API_KEY or "
                "OPENAI_API_KEY to enable PDF policy extraction."
            )
    if provider == "anthropic":
        if not settings.anthropic_api_key:
            raise ExtractionError("EXTRACTION_PROVIDER=anthropic but ANTHROPIC_API_KEY is not set.")
        return ClaudePolicyExtractor()
    if provider == "openai":
        if not settings.openai_api_key:
            raise ExtractionError("EXTRACTION_PROVIDER=openai but OPENAI_API_KEY is not set.")
        return OpenAIPolicyExtractor()
    raise ExtractionError(f"Unknown EXTRACTION_PROVIDER '{provider}'.")


# --- conversion to the policy document -----------------------------------------------------


def _coerce(operator: str | None, value: object) -> object:
    """Bends the extracted value to the operator's shape.

    Models routinely put a single option in the list slot ("options": ["CA"]) and then use a
    scalar operator, or the reverse; both are unambiguous, so fix them here rather than drop the
    rule and make a reviewer re-type it.
    """
    op = OPERATORS.get(operator or "")
    if op is None:
        return value
    if op.shape is ValueShape.SCALAR and isinstance(value, list) and len(value) == 1:
        return value[0]
    if op.shape is ValueShape.LIST and not isinstance(value, list) and value is not None:
        return [value]
    if op.shape is ValueShape.NONE:
        return None
    return value


def _condition(c: ExtractedCondition) -> JsonDict:
    return {
        "field": c.field,
        "operator": c.operator,
        "value": _coerce(c.operator, c.value.resolve()),
        "label": c.label,
    }


def _rule(r: ExtractedRule) -> JsonDict:
    return {
        "kind": r.kind,
        "label": r.label,
        "category": r.category if r.category in CATEGORIES else "other",
        "severity": r.severity,
        "field": r.field,
        "operator": r.operator,
        "value": _coerce(r.operator, r.value.resolve() if r.value else None),
        "alternatives": [_condition(c) for c in r.alternatives],
        "applies_when": [_condition(c) for c in r.applies_when],
        "message_template": None,
        "source_quote": r.source_quote,
    }


JsonDict = dict[str, Any]


def to_policy_dict(extracted: ExtractedPolicy) -> JsonDict:
    return {
        "rules": [_rule(r) for r in extracted.rules],
        "programs": [
            {
                "name": p.name,
                "rank": p.rank,
                "description": p.description,
                "applies_when": [_condition(c) for c in p.applies_when],
                "details": {d.key: d.value for d in p.details},
                "rules": [_rule(r) for r in p.rules],
            }
            for p in extracted.programs
        ],
    }


class DraftPolicy(BaseModel):
    policy: JsonDict
    # Rules the engine rejected (unknown field, wrong value type, ...) are dropped from the
    # draft and reported here, so the reviewer sees them rather than a failed job.
    dropped: list[Uncertainty]


def build_draft(extracted: ExtractedPolicy) -> DraftPolicy:
    """Validates rule by rule so one bad rule costs one rule, not the whole extraction."""
    dropped: list[Uncertainty] = []

    def keep(rule: JsonDict, where: str) -> bool:
        try:
            Policy.model_validate({"lender_id": "x", "lender_name": "x", "rules": [rule]})
            return True
        except ValidationError as error:
            reason = "; ".join(e["msg"] for e in error.errors())
            dropped.append(
                Uncertainty(
                    item=f"{where}: rule '{rule['label']}' was dropped",
                    reason=reason,
                    suggestion="Re-create it in the editor with a catalog field and operator.",
                )
            )
            return False

    raw = to_policy_dict(extracted)
    rules = [r for r in raw["rules"] if keep(r, "Lender-wide")]
    programs = []
    for program in raw["programs"]:
        try:
            Policy.model_validate(
                {"lender_id": "x", "lender_name": "x",
                 "programs": [{**program, "rules": []}]}
            )  # fmt: skip
        except ValidationError as error:
            dropped.append(
                Uncertainty(
                    item=f"Program '{program['name']}' was dropped",
                    reason="; ".join(e["msg"] for e in error.errors()),
                    suggestion="Add the program in the editor and set its conditions there.",
                )
            )
            continue
        program["rules"] = [r for r in program["rules"] if keep(r, program["name"])]
        programs.append(program)
    return DraftPolicy(policy={"rules": rules, "programs": programs}, dropped=dropped)


def dump_json(extracted: ExtractedPolicy) -> str:
    return json.dumps(extracted.model_dump(), indent=2)
