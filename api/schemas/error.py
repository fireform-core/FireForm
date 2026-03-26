"""Standard API error envelope for all JSON error responses."""

from __future__ import annotations

from typing import Any, Optional, Union

from pydantic import BaseModel, Field


class ErrorResponse(BaseModel):
    """Consistent JSON shape for every API error."""

    status_code: int = Field(..., description="HTTP status code")
    code: str = Field(..., description="Stable application error identifier")
    message: str = Field(..., description="Human-readable summary")
    details: Optional[Union[dict, list]] = Field(
        None,
        description="Extra context (e.g. validation errors)",
    )


def error_body(
    *,
    status_code: int,
    code: str,
    message: str,
    details: Any = None,
) -> dict:
    """Serialize to JSON-compatible dict for JSONResponse."""
    return ErrorResponse(
        status_code=status_code,
        code=code,
        message=message,
        details=details,
    ).model_dump()
