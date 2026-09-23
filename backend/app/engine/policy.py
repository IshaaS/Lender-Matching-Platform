import re
from typing import Any, Literal, Self

from pydantic import BaseModel, Field, model_validator

from app.engine.catalog import CATALOG, FieldType
from app.engine.operators import OPERATORS, ValueShape

Severity = Literal["hard", "soft"]
DecisionMode = Literal["automatic", "manual_review"]

ALLOWED_TEMPLATE_PLACEHOLDERS = {"field", "actual", "expected"}


def _validate_message_template(template: str) -> None:
    placeholders = re.findall(r"\{([^{}]+)\}", template)
    for p in placeholders:
        var_name = p.split(":")[0].strip()
        if var_name not in ALLOWED_TEMPLATE_PLACEHOLDERS:
            raise ValueError(
                f"Invalid placeholder '{{{p}}}' in message_template. "
                "Allowed placeholders are: {field}, {actual}, {expected}."
            )


def _check_condition(field_key: str, operator: str, value: Any) -> None:
    if field_key not in CATALOG:
        raise ValueError(f"Unknown field '{field_key}'")
    if operator not in OPERATORS:
        raise ValueError(f"Unknown operator '{operator}'")
    fdef, op = CATALOG[field_key], OPERATORS[operator]
    if fdef.type not in op.field_types:
        raise ValueError(f"Operator '{operator}' cannot be used on {fdef.type} field '{field_key}'")

    def is_number(v: Any) -> bool:
        return isinstance(v, int | float) and not isinstance(v, bool)

    match op.shape:
        case ValueShape.NONE:
            return
        case ValueShape.SCALAR:
            if fdef.type is FieldType.NUMBER and not is_number(value):
                raise ValueError(f"'{field_key}' needs a numeric value, got {value!r}")
            if fdef.type is FieldType.BOOLEAN and not isinstance(value, bool):
                raise ValueError(f"'{field_key}' needs true/false, got {value!r}")
            if fdef.type is FieldType.ENUM and value not in fdef.options:
                raise ValueError(f"{value!r} is not a valid option for '{field_key}'")
        case ValueShape.RANGE:
            if (
                not isinstance(value, list)
                or len(value) != 2
                or not all(is_number(v) for v in value)
                or value[0] > value[1]
            ):
                raise ValueError(f"'{operator}' needs [min, max], got {value!r}")
        case ValueShape.LIST:
            if not isinstance(value, list) or not value:
                raise ValueError(f"'{operator}' needs a non-empty list, got {value!r}")
            unknown = [v for v in value if v not in fdef.options]
            if unknown:
                raise ValueError(f"Invalid options for '{field_key}': {unknown}")


class Condition(BaseModel):
    field: str
    operator: str
    value: Any = None
    label: str | None = None

    @model_validator(mode="after")
    def _validate(self) -> Self:
        _check_condition(self.field, self.operator, self.value)
        return self


class Rule(BaseModel):
    id: str | None = None
    kind: Literal["simple", "any_of"] = "simple"
    label: str
    category: str = "other"
    severity: Severity = "hard"
    # simple
    field: str | None = None
    operator: str | None = None
    value: Any = None
    # any_of
    alternatives: list[Condition] = Field(default_factory=list)
    # The rule is skipped (neither pass nor fail) unless every condition holds.
    applies_when: list[Condition] = Field(default_factory=list)
    message_template: str | None = None
    # Provenance
    source_document: str | None = None
    source_quote: str | None = None
    source_page: int | None = None

    @model_validator(mode="after")
    def _validate(self) -> Self:
        if self.message_template:
            _validate_message_template(self.message_template)
        if self.kind == "simple":
            if not self.field or not self.operator:
                raise ValueError("A simple rule needs a field and an operator")
            _check_condition(self.field, self.operator, self.value)
        elif not self.alternatives:
            raise ValueError("An any_of rule needs at least one alternative")
        return self


class Program(BaseModel):
    id: str | None = None
    name: str
    rank: int = Field(ge=1)
    decision_mode: DecisionMode = "automatic"
    description: str | None = None
    applies_when: list[Condition] = Field(default_factory=list)
    rules: list[Rule] = Field(default_factory=list)
    details: dict[str, Any] = Field(default_factory=dict)


class Policy(BaseModel):
    lender_id: str
    lender_name: str
    version_id: str | None = None
    version_number: int = 1
    # Lender-wide restrictions, evaluated before any program.
    rules: list[Rule] = Field(default_factory=list)
    programs: list[Program] = Field(default_factory=list)

