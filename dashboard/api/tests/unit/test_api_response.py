"""Unit tests for the ApiResponse helper class."""

import json
from http import HTTPStatus

from api_response import ApiResponse
from flask import Flask


class TestApiResponseSuccess:
    """Tests for ApiResponse.success()."""

    def test_returns_json_response(self, app: Flask) -> None:
        """Success response should return valid JSON."""
        with app.app_context():
            response = ApiResponse.success({"key": "value"})

            assert response.content_type == "application/json"
            data = json.loads(response.data)
            assert data["success"] is True
            assert data["data"] == {"key": "value"}

    def test_default_status_code(self, app: Flask) -> None:
        """Default status code should be 200 OK."""
        with app.app_context():
            response = ApiResponse.success({})
            assert response.status_code == HTTPStatus.OK

    def test_custom_status_code(self, app: Flask) -> None:
        """Should accept custom status codes."""
        with app.app_context():
            response = ApiResponse.success({}, HTTPStatus.CREATED)
            assert response.status_code == HTTPStatus.CREATED

    def test_none_data(self, app: Flask) -> None:
        """Should handle None data gracefully."""
        with app.app_context():
            response = ApiResponse.success(None)
            data = json.loads(response.data)
            assert data["data"] is None


class TestApiResponseError:
    """Tests for ApiResponse.error()."""

    def test_returns_error_json(self, app: Flask) -> None:
        """Error response should include error message."""
        with app.app_context():
            response = ApiResponse.error("Something went wrong")

            data = json.loads(response.data)
            assert data["success"] is False
            assert "Something went wrong" in data["message"]

    def test_handles_exception_objects(self, app: Flask) -> None:
        """Should extract message from Exception objects."""
        with app.app_context():
            exc = ValueError("Invalid input")
            response = ApiResponse.error(exc)

            data = json.loads(response.data)
            assert "Invalid input" in data["message"]

    def test_default_error_status(self, app: Flask) -> None:
        """Default error status should be 500."""
        with app.app_context():
            response = ApiResponse.error("Error")
            assert response.status_code == HTTPStatus.INTERNAL_SERVER_ERROR

    def test_custom_error_status(self, app: Flask) -> None:
        """Should accept custom error status codes."""
        with app.app_context():
            response = ApiResponse.error("Not found", HTTPStatus.NOT_FOUND)
            assert response.status_code == HTTPStatus.NOT_FOUND
