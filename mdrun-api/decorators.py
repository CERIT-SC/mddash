import functools
import logging
from typing import Callable

from extensions import db
from flask import Response, jsonify
from marshmallow import ValidationError
from werkzeug.exceptions import HTTPException

logger = logging.getLogger(__name__)


def handle_exceptions(rollback: bool = False) -> Callable:
    """Catch exceptions and return {detail: "..."} JSON responses."""

    def decorator(f: Callable[..., Response]) -> Callable[..., Response]:
        @functools.wraps(f)
        def wrapper(*args: object, **kwargs: object) -> Response:
            try:
                return f(*args, **kwargs)
            except Exception as e:
                if rollback:
                    db.session.rollback()

                exc_info = False

                if isinstance(e, ValidationError):
                    status = 400
                    message = e.messages if getattr(e, "messages", None) else str(e)
                elif isinstance(e, HTTPException):
                    status = e.code or 500
                    message = e.description or "Unknown error occurred."
                else:
                    status = 500
                    message = str(e)
                    exc_info = True

                logger.error(message, exc_info=exc_info)

                response = jsonify({"detail": message})
                response.status_code = int(status)
                return response

        return wrapper

    return decorator