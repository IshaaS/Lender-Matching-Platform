from typing import Any, NoReturn

from fastapi import HTTPException


def fail(status: int, message: str, errors: list[Any] | None = None) -> NoReturn:
    """Every API error has the same body: {"detail": {"message": ..., "errors": [...]}}."""
    raise HTTPException(status, detail={"message": message, "errors": errors or []})
