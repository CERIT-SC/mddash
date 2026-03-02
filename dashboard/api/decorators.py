import functools
from typing import Callable

from api_response import ApiResponse
from extensions import db
from flask import Response


def handle_exceptions(rollback: bool = False) -> Callable:
    """
    Handle exceptions in Flask routes decorator.

    Args:
        rollback: Whether to rollback database session on exception (default: False)

    Returns:
        Callable: A decorator that wraps route functions with exception handling.
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
