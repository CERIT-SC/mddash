import functools
from typing import Callable
from flask import Response

from api_response import ApiResponse
from extensions import db


def handle_exceptions(rollback: bool = False) -> Callable:
    def decorator(f: Callable[..., Response]) -> Callable[..., Response]:
        @functools.wraps(f)
        def wrapper(*args, **kwargs) -> Response:
            try:
                return f(*args, **kwargs)
            except Exception as e:
                if rollback:
                    db.session.rollback()
                return ApiResponse.error(e)
        return wrapper
    return decorator
