"""RFC 9457 problem-details error handling (FastAPI/Starlette). Body: `{type, title, detail[, solution]}`."""

import logging
from http import HTTPStatus
from typing import ClassVar

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

logger = logging.getLogger(__name__)


class ApiError(HTTPException):
    """
    HTTPException with a value-add type token and optional user-facing solution.

    Raise at known-error sites; the global handler renders it as RFC 9457 JSON.
    Plain HTTPExceptions (404/405/...) also work. The handler upgrades them to an
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


class _StatusError(ApiError):
    """Generic error for one HTTP status; the type token is derived from the status name."""

    status: ClassVar[HTTPStatus]
    token: ClassVar[str]

    def __init__(self, description: str | None = None) -> None:
        super().__init__(self.status, description or self.status.phrase, f"urn:mddash:{self.token}")


class BadRequest(_StatusError):  # ruff:ignore[error-suffix-on-exception-name]
    """400 with token `bad-request`."""

    status = HTTPStatus.BAD_REQUEST
    token = "bad-request"


class Unauthorized(_StatusError):  # ruff:ignore[error-suffix-on-exception-name]
    """401 with token `unauthorized`."""

    status = HTTPStatus.UNAUTHORIZED
    token = "unauthorized"


class Forbidden(_StatusError):  # ruff:ignore[error-suffix-on-exception-name]
    """403 with token `forbidden`."""

    status = HTTPStatus.FORBIDDEN
    token = "forbidden"


class NotFound(_StatusError):  # ruff:ignore[error-suffix-on-exception-name]
    """404 with token `not-found`."""

    status = HTTPStatus.NOT_FOUND
    token = "not-found"


class Conflict(_StatusError):  # ruff:ignore[error-suffix-on-exception-name]
    """409 with token `conflict`."""

    status = HTTPStatus.CONFLICT
    token = "conflict"


class UnprocessableEntity(_StatusError):  # ruff:ignore[error-suffix-on-exception-name]
    """422 with token `unprocessable-entity`."""

    status = HTTPStatus.UNPROCESSABLE_ENTITY
    token = "unprocessable-entity"


class InternalServerError(_StatusError):
    """500 with token `internal-server-error`."""

    status = HTTPStatus.INTERNAL_SERVER_ERROR
    token = "internal-server-error"


_LOC_KINDS = {"body", "query", "path", "header", "cookie"}


def flatten_validation(errors: list[dict]) -> str:
    """Flatten FastAPI RequestValidationError errors into a single readable line."""
    parts: list[str] = []
    for err in errors:
        loc = list(err.get("loc", []))
        # FastAPI prefixes the parameter kind; a field may itself be named "query" or "path".
        if loc and loc[0] in _LOC_KINDS:
            loc = loc[1:]
        loc = ".".join(str(p) for p in loc)
        msg = err.get("msg", "")
        parts.append(f"{loc}: {msg}" if loc else msg)
    return "; ".join(p for p in parts if p)


def register_exception_handlers(app: FastAPI) -> None:
    """Register global exception handlers returning RFC 9457 problem details."""

    @app.exception_handler(RequestValidationError)
    def _validation(request: Request, exc: RequestValidationError) -> JSONResponse:
        detail = flatten_validation(list(exc.errors()))
        logger.warning("Validation error on %s %s: %s", request.method, request.url.path, detail)
        return ApiError(400, detail or "Invalid request.", "urn:mddash:validation-error").to_response()

    @app.exception_handler(StarletteHTTPException)
    def _http(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        if not isinstance(exc, ApiError):
            name = HTTPStatus(exc.status_code).phrase
            api_err = ApiError(
                exc.status_code,
                str(exc.detail),
                f"urn:mddash:{name.lower().replace(' ', '-')}",
            )
            api_err.headers = exc.headers
        else:
            api_err = exc
        code = api_err.status_code
        logger.log(
            logging.WARNING if code < HTTPStatus.INTERNAL_SERVER_ERROR else logging.ERROR,
            "%s %s -> %s [%s]: %s",
            request.method,
            request.url.path,
            code,
            api_err.problem_type,
            api_err.detail,
            # Starlette runs sync handlers outside the `except` block: pass the exception itself.
            exc_info=exc if code >= HTTPStatus.INTERNAL_SERVER_ERROR else None,
        )
        return api_err.to_response()

    @app.exception_handler(Exception)
    def _unhandled(request: Request, exc: Exception) -> JSONResponse:
        # Starlette calls this outside the `except` block: pass the exception itself.
        logger.error("Unhandled exception on %s %s", request.method, request.url.path, exc_info=exc)
        return ApiError(
            500,
            "Internal server error. Please try again later.",
            "urn:mddash:internal-error",
            "Try again in a moment; if the problem persists, contact support.",
        ).to_response()
