"""Operator registry. Each operator is a pure function plus the metadata the validator,
message builder and policy editor need.

Adding a new comparison style = one `register(...)` call. Nothing else changes.
"""

from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from app.engine.catalog import FieldType


class ValueShape(StrEnum):
    NONE = "none"  # is_true / is_false take no comparison value
    SCALAR = "scalar"
    RANGE = "range"  # [min, max]
    LIST = "list"


@dataclass(frozen=True)
class Operator:
    key: str
    label: str
    shape: ValueShape
    field_types: tuple[FieldType, ...]
    test: Callable[[Any, Any], bool]
    # Sentence fragments: "{field} is {actual}, <fail>" / "{field} is {actual} (<requirement>)"
    requirement: str
    fail: str
    # +1: higher actual is better (gte); -1: lower is better (lte); 0: no headroom concept
    direction: int = 0


OPERATORS: dict[str, Operator] = {}


def register(op: Operator) -> Operator:
    if op.key in OPERATORS:
        raise ValueError(f"Operator '{op.key}' is already registered")
    OPERATORS[op.key] = op
    return op


def get_operator(key: str) -> Operator:
    try:
        return OPERATORS[key]
    except KeyError:
        raise KeyError(f"Unknown operator '{key}'") from None


_NUM = (FieldType.NUMBER,)
_ANY = (FieldType.NUMBER, FieldType.ENUM, FieldType.BOOLEAN)

register(
    Operator(
        "gte",
        "at least",
        ValueShape.SCALAR,
        _NUM,
        lambda a, e: a >= e,
        "minimum {expected}",
        "below the minimum of {expected}",
        direction=1,
    )
)
register(
    Operator(
        "gt",
        "more than",
        ValueShape.SCALAR,
        _NUM,
        lambda a, e: a > e,
        "must exceed {expected}",
        "not above {expected}",
        direction=1,
    )
)
register(
    Operator(
        "lte",
        "at most",
        ValueShape.SCALAR,
        _NUM,
        lambda a, e: a <= e,
        "maximum {expected}",
        "above the maximum of {expected}",
        direction=-1,
    )
)
register(
    Operator(
        "lt",
        "less than",
        ValueShape.SCALAR,
        _NUM,
        lambda a, e: a < e,
        "must be under {expected}",
        "not under {expected}",
        direction=-1,
    )
)
register(
    Operator(
        "between",
        "between",
        ValueShape.RANGE,
        _NUM,
        lambda a, e: e[0] <= a <= e[1],
        "must be between {expected}",
        "outside the accepted range of {expected}",
    )
)
register(
    Operator(
        "eq",
        "is",
        ValueShape.SCALAR,
        _ANY,
        lambda a, e: a == e,
        "must be {expected}",
        "but must be {expected}",
    )
)
register(
    Operator(
        "neq",
        "is not",
        ValueShape.SCALAR,
        _ANY,
        lambda a, e: a != e,
        "must not be {expected}",
        "which is not accepted",
    )
)
register(
    Operator(
        "in",
        "is one of",
        ValueShape.LIST,
        (FieldType.ENUM,),
        lambda a, e: a in e,
        "accepted: {expected}",
        "which is not among the accepted values ({expected})",
    )
)
register(
    Operator(
        "not_in",
        "is none of",
        ValueShape.LIST,
        (FieldType.ENUM,),
        lambda a, e: a not in e,
        "not on the exclusion list",
        "which is on this lender's exclusion list",
    )
)
register(
    Operator(
        "is_true",
        "is yes",
        ValueShape.NONE,
        (FieldType.BOOLEAN,),
        lambda a, _e: a is True,
        "required",
        "but this is required",
    )
)
register(
    Operator(
        "is_false",
        "is no",
        ValueShape.NONE,
        (FieldType.BOOLEAN,),
        lambda a, _e: a is False,
        "must be no",
        "which this lender does not accept",
    )
)
