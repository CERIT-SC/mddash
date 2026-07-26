"""RFC 9457 problem-details error handling (no DB, no marshmallow)."""

import logging
from http import HTTPStatus

from flask import Flask, Response, jsonify, request
from werkzeug.exceptions import HTTPException

logger = logging.getLogger(__name__)


def problem(title: str, detail: str, status: int, type_: str = "about:blank") -> Response:
    """Build an RFC 9457 problem-details JSON response."""
    resp = jsonify({"type": type_, "title": title, "detail": detail})
    resp.mimetype = "application/problem+json"
    resp.status_code = status
    return resp


def register_error_handlers(app: Flask) -> None:
    """Register global error handlers returning RFC 9457 problem details."""

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
        logger.error("Unhandled exception on %s %s", request.method, request.path, exc_info=True)  # ruff:ignore[exc-info-outside-except-handler]
        return problem("Internal Server Error", "Internal server error. Please try again later.", 500)
