import functools
from typing import Callable

from api_response import ApiResponse
from extensions import db
from flask import Response


def handle_exceptions(rollback: bool = False) -> Callable:
    """
    Catch exceptions and return standardized error responses.

    Args:
        rollback: Whether to rollback the database session on error.

    Returns:
        Callable: A decorator function that wraps the target function.
    """

    def decorator(f: Callable[..., Response]) -> Callable[..., Response]:
        @functools.wraps(f)
        def wrapper(*args: object, **kwargs: object) -> Response:
            try:
                return f(*args, **kwargs)
            except Exception as e:
                if rollback:
                    db.session.rollback()
                return ApiResponse.error(e)

        return wrapper

    return decorator
