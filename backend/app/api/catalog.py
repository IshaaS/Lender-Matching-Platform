from typing import Any

from fastapi import APIRouter

from app.engine.catalog import CATEGORIES, FIELDS
from app.engine.operators import OPERATORS

router = APIRouter(prefix="/catalog", tags=["lender policies"])


@router.get("")
def read_catalog() -> dict[str, Any]:
    """Everything the rule editor needs: testable fields, operators and which go together."""
    return {
        "categories": CATEGORIES,
        "fields": [
            {
                "key": f.key, "label": f.label, "type": f.type, "category": f.category,
                "unit": f.unit, "options": f.options, "derived": f.derived,
                "description": f.description,
                "operators": [op.key for op in OPERATORS.values() if f.type in op.field_types],
            }
            for f in FIELDS
        ],
        "operators": [
            {"key": op.key, "label": op.label, "value_shape": op.shape} for op in OPERATORS.values()
        ],
    }  # fmt: skip
