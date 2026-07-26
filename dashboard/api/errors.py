"""RFC 9457 problem-details error handling."""

import logging
from http import HTTPStatus

from extensions import db
from flask import Flask, Response, jsonify, request
from marshmallow import ValidationError
from werkzeug.exceptions import HTTPException

logger = logging.getLogger(__name__)


def problem(title: str, detail: str, status: int, type_: str = "about:blank") -> Response:
    """Build an RFC 9457 problem-details JSON response."""
    resp = jsonify({"type": type_, "title": title, "detail": detail})
    resp.mimetype = "application/problem+json"
    resp.status_code = status
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
        return problem("Bad Request", detail, 400)

    @app.errorhandler(HTTPException)
    def _http(exc: HTTPException) -> Response:
        code = exc.code or 500
        detail = exc.description or "An error occurred."
        logger.log(
            logging.WARNING if code < HTTPStatus.INTERNAL_SERVER_ERROR else logging.ERROR,
            "%s %s -> %s: %s",
            request.method,
            request.path,
            code,
            detail,
            exc_info=code >= HTTPStatus.INTERNAL_SERVER_ERROR,
        )
        return problem(exc.name, detail, code)

    @app.errorhandler(Exception)
    def _unhandled(_exc: Exception) -> Response:
        db.session.rollback()
        logger.error("Unhandled exception on %s %s", request.method, request.path, exc_info=True)  # ruff:ignore[exc-info-outside-except-handler]
        return problem("Internal Server Error", "Internal server error. Please try again later.", 500)
