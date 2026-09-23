"""Human-readable values and criterion messages."""

from typing import Any

from app.engine.catalog import FieldDef, Unit
from app.engine.operators import Operator, ValueShape


def humanize(token: str) -> str:
    return token.replace("_", " ")


def _number(value: float) -> str:
    return f"{value:,.0f}" if float(value).is_integer() else f"{value:,.1f}"


def format_value(fdef: FieldDef, value: Any) -> str:
    if value is None:
        return "not provided"
    if isinstance(value, bool):
        return "yes" if value else "no"
    if isinstance(value, list):
        return ", ".join(format_value(fdef, v) for v in value)
    if isinstance(value, int | float):
        n = _number(value)
        match fdef.unit:
            case Unit.MONEY:
                return f"${n}"
            case Unit.PERCENT:
                return f"{n}%"
            case Unit.YEARS:
                return f"{n} year{'' if value == 1 else 's'}"
            case Unit.MONTHS:
                return f"{n} months"
            case Unit.MILES:
                return f"{n} miles"
            case _:
                return n
    text = str(value)
    # State codes and similar short upper-case tokens read better untouched.
    return text if text.isupper() else humanize(text)


def format_expected(fdef: FieldDef, op: Operator, expected: Any) -> str:
    if op.shape is ValueShape.NONE:
        return ""
    if op.shape is ValueShape.RANGE:
        return f"{format_value(fdef, expected[0])} – {format_value(fdef, expected[1])}"
    return format_value(fdef, expected)


def build_message(
    fdef: FieldDef, op: Operator, expected: Any, actual: Any, passed: bool, template: str | None
) -> str:
    actual_text = format_value(fdef, actual)
    expected_text = format_expected(fdef, op, expected)
    if template and not passed:
        return template.format(field=fdef.label, actual=actual_text, expected=expected_text)
    if actual is None:
        requirement = op.requirement.format(expected=expected_text)
        return f"{fdef.label} was not provided ({requirement})."
    if passed:
        return f"{fdef.label} is {actual_text} ({op.requirement.format(expected=expected_text)})."
    return f"{fdef.label} is {actual_text}, {op.fail.format(expected=expected_text)}."
