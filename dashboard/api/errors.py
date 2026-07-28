"""RFC 9457 problem-details error handling. Body: `{type, title, detail[, solution]}`."""

import logging
from http import HTTPStatus

from extensions import db
from flask import Flask, Response, jsonify, request
from marshmallow import ValidationError
from werkzeug.exceptions import HTTPException

logger = logging.getLogger(__name__)


class ApiError(HTTPException):
    """
    HTTPException with a value-add type token and optional user-facing solution.

    Raise at known-error sites; the global handler renders it as RFC 9457 JSON.
    Plain werkzeug exceptions (Conflict/NotFound/...) also work — the handler
    upgrades them to an ApiError with a token derived from the HTTP phrase.
    """

    problem_type: str
    problem_solution: str | None
    code: int  # type: ignore[assignment]  # narrows the base HTTPException.code (int | None)

    def __init__(self, code: int, description: str, type_: str, solution: str | None = None) -> None:
        """Construct a known error: HTTP `code`, `description` (cause), `type_` token, optional `solution`."""
        super().__init__(description=description)
        self.code = code
        self.problem_type = type_
        self.problem_solution = solution

    def to_response(self) -> Response:
        """Render this error as an RFC 9457 problem-details JSON response."""
        body: dict[str, str] = {
            "type": self.problem_type,
            "title": HTTPStatus(self.code).phrase,
            "detail": self.description or "An error occurred.",
        }
        if self.problem_solution is not None:
            body["solution"] = self.problem_solution
        resp = jsonify(body)
        resp.mimetype = "application/problem+json"
        resp.status_code = self.code
        return resp


def flatten_messages(messages: object) -> str:
    """Flatten marshmallow ValidationError.messages into a single string."""
    if isinstance(messages, str):
        return messages
    if isinstance(messages, list):
        return "; ".join(flatten_messages(m) for m in messages)
    if isinstance(messages, dict):
        parts: list[str] = []
        for key, value in messages.items():
            flat = flatten_messages(value)
            parts.append(f"{key}: {flat}" if flat else str(key))
        return "; ".join(parts)
    return str(messages)


def register_error_handlers(app: Flask) -> None:
    """Register global error handlers returning RFC 9457 problem details."""

    @app.errorhandler(ValidationError)
    def _validation(exc: ValidationError) -> Response:
        detail = flatten_messages(exc.messages)
        logger.warning("Validation error on %s %s: %s", request.method, request.path, detail)
        return ApiError(400, detail, "urn:mddash:validation-error").to_response()

    @app.errorhandler(HTTPException)
    def _http(exc: HTTPException) -> Response:
        if not isinstance(exc, ApiError):
            name = exc.name or "Internal Server Error"
            exc = ApiError(
                exc.code or 500,
                exc.description or "An error occurred.",
                f"urn:mddash:{name.lower().replace(' ', '-')}",
            )
        code = exc.code or 500
        logger.log(
            logging.WARNING if code < HTTPStatus.INTERNAL_SERVER_ERROR else logging.ERROR,
            "%s %s -> %s [%s]: %s",
            request.method,
            request.path,
            code,
            exc.problem_type,
            exc.description,
            exc_info=code >= HTTPStatus.INTERNAL_SERVER_ERROR,
        )
        return exc.to_response()

    @app.errorhandler(Exception)
    def _unhandled(_exc: Exception) -> Response:
        db.session.rollback()
        logger.error(
            "Unhandled exception on %s %s",
            request.method,
            request.path,
            exc_info=True,  # ruff:ignore[exc-info-outside-except-handler]
        )
        return ApiError(
            500,
            "Internal server error. Please try again later.",
            "urn:mddash:internal-error",
            "Try again in a moment; if the problem persists, contact support.",
        ).to_response()
