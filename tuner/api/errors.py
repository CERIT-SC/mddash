"""RFC 9457 problem-details error handling (FastAPI/Starlette). Body: `{type, title, detail[, solution]}`."""

import logging
from http import HTTPStatus

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

logger = logging.getLogger(__name__)


class ApiError(HTTPException):
    """
    HTTPException with a value-add type token and optional user-facing solution.

    Raise at known-error sites; the global handler renders it as RFC 9457 JSON.
    Plain HTTPExceptions (404/413/...) also work — the handler upgrades them to an
    ApiError with a token derived from the HTTP phrase.
    """

    problem_type: str
    problem_solution: str | None

    def __init__(self, code: int, description: str, type_: str, solution: str | None = None) -> None:
        """Construct a known error: HTTP `code`, `description` (cause), `type_` token, optional `solution`."""
        super().__init__(status_code=code, detail=description)
        self.problem_type = type_
        self.problem_solution = solution

    def to_response(self) -> JSONResponse:
        """Render this error as an RFC 9457 problem-details JSON response."""
        body: dict[str, str] = {
            "type": self.problem_type,
            "title": HTTPStatus(self.status_code).phrase,
            "detail": str(self.detail) or "An error occurred.",
        }
        if self.problem_solution is not None:
            body["solution"] = self.problem_solution
        return JSONResponse(
            status_code=self.status_code,
            content=body,
            media_type="application/problem+json",
            headers=self.headers,
        )


def _flatten_validation(errors: list[dict]) -> str:
    """Flatten FastAPI RequestValidationError errors into a single readable line."""
    parts: list[str] = []
    for err in errors:
        loc = ".".join(str(p) for p in err.get("loc", []) if p != "body")
        msg = err.get("msg", "")
        parts.append(f"{loc}: {msg}" if loc else msg)
    return "; ".join(p for p in parts if p)


def register_exception_handlers(app: FastAPI) -> None:
    """Register global exception handlers returning RFC 9457 problem details."""

    @app.exception_handler(RequestValidationError)
    def _validation(_req: Request, exc: RequestValidationError) -> JSONResponse:
        detail = _flatten_validation(list(exc.errors()))
        logger.warning("Validation error: %s", detail)
        return ApiError(400, detail or "Invalid request.", "urn:mddash:validation-error").to_response()

    @app.exception_handler(StarletteHTTPException)
    def _http(_req: Request, exc: StarletteHTTPException) -> JSONResponse:
        if not isinstance(exc, ApiError):
            name = HTTPStatus(exc.status_code).phrase
            api_err = ApiError(
                exc.status_code,
                str(exc.detail) if exc.detail is not None else "An error occurred.",
                f"urn:mddash:{name.lower().replace(' ', '-')}",
            )
            api_err.headers = exc.headers
        else:
            api_err = exc
        code = api_err.status_code
        logger.log(
            logging.WARNING if code < HTTPStatus.INTERNAL_SERVER_ERROR else logging.ERROR,
            "-> %s [%s]: %s",
            code,
            api_err.problem_type,
            api_err.detail,
            exc_info=code >= HTTPStatus.INTERNAL_SERVER_ERROR,
        )
        return api_err.to_response()

    @app.exception_handler(Exception)
    def _unhandled(_req: Request, _exc: Exception) -> JSONResponse:
        logger.error("Unhandled exception", exc_info=True)  # ruff:ignore[exc-info-outside-except-handler]
        return ApiError(
            500,
            "Internal server error. Please try again later.",
            "urn:mddash:internal-error",
            "Try again in a moment; if the problem persists, contact support.",
        ).to_response()
