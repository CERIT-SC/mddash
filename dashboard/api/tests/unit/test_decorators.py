"""Unit tests for the handle_exceptions decorator."""

from typing import NoReturn

from flask import Flask, Response


class TestHandleExceptionsDecorator:
    """Tests for the @handle_exceptions decorator."""

    def test_passes_through_on_success(self, app: Flask) -> None:
        """Decorator should not interfere with successful responses."""
        from api_response import ApiResponse
        from decorators import handle_exceptions

        @handle_exceptions()
        def successful_route() -> Response:
            return ApiResponse.success({"result": "ok"})

        with app.app_context():
            response = successful_route()
            assert response.status_code == 200

    def test_catches_exceptions(self, app: Flask) -> None:
        """Decorator should catch and convert exceptions to error responses."""
        from decorators import handle_exceptions

        @handle_exceptions()
        def failing_route() -> NoReturn:
            raise ValueError("Test error")

        with app.app_context():
            response = failing_route()
            assert response.status_code == 500
            assert b"Test error" in response.data

    def test_rollback_on_exception(self, app: Flask) -> None:
        """Decorator with rollback=True should rollback DB on exception."""
        from decorators import handle_exceptions
        from extensions import db

        rollback_called = False
        original_rollback = db.session.rollback

        def tracking_rollback() -> None:
            nonlocal rollback_called
            rollback_called = True
            original_rollback()

        @handle_exceptions(rollback=True)
        def route_with_rollback() -> NoReturn:
            raise ValueError("DB error")

        with app.app_context():
            db.session.rollback = tracking_rollback
            try:
                route_with_rollback()
                assert rollback_called
            finally:
                db.session.rollback = original_rollback

    def test_no_rollback_by_default(self, app: Flask) -> None:
        """Decorator without rollback=True should not rollback on exception."""
        from decorators import handle_exceptions
        from extensions import db

        rollback_called = False
        original_rollback = db.session.rollback

        def tracking_rollback() -> None:
            nonlocal rollback_called
            rollback_called = True
            original_rollback()

        @handle_exceptions()
        def route_without_rollback() -> NoReturn:
            raise ValueError("Some error")

        with app.app_context():
            db.session.rollback = tracking_rollback
            try:
                route_without_rollback()
                assert not rollback_called
            finally:
                db.session.rollback = original_rollback
