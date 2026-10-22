"""OpenAPI response declarations shared by the routers."""

from typing import Any

PROBLEM_CONTENT = {"application/problem+json": {"schema": {"$ref": "#/components/schemas/Problem"}}}

_DESCRIPTIONS = {
    400: "Invalid request",
    401: "Authentication required",
    403: "Operation forbidden",
    404: "Resource not found",
    409: "Resource conflict",
    422: "Resource could not be processed",
    503: "Service unavailable",
}


def problems(*codes: int) -> dict[int | str, dict[str, Any]]:
    """Problem-details responses for `codes`, plus the catch-all `default`."""
    responses: dict[int | str, dict[str, Any]] = {
        code: {"description": _DESCRIPTIONS[code], "content": PROBLEM_CONTENT} for code in codes
    }
    responses["default"] = {"description": "RFC 9457 problem details", "content": PROBLEM_CONTENT}
    return responses
