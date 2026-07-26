"""Tests for RFC 9457 problem-details error handling."""

from http import HTTPStatus

import pytest
from flask import Flask
from flask.testing import FlaskClient
from flask.typing import ResponseReturnValue
from marshmallow import ValidationError


class TestProblemResponse:
    """Tests for problem() and flatten_messages()."""

    def test_problem_sets_content_type_and_status(self, app: Flask) -> None:
        """problem() returns correct status, mimetype, and body fields."""
        with app.test_request_context():
            from errors import problem

            resp = problem("Not Found", "Resource missing", 404)
            assert resp.status_code == 404
            assert resp.mimetype == "application/problem+json"
            data = resp.get_json()
            assert data["type"] == "about:blank"
            assert data["title"] == "Not Found"
            assert data["detail"] == "Resource missing"

    def test_problem_no_status_in_body(self, app: Flask) -> None:
        """Status code must not appear in the JSON body."""
        with app.test_request_context():
            from errors import problem

            resp = problem("Error", "msg", 500)
            assert "status" not in resp.get_json()

    def test_flatten_string(self) -> None:
        """Strings pass through unchanged."""
        from errors import flatten_messages

        assert flatten_messages("simple message") == "simple message"

    def test_flatten_list(self) -> None:
        """Lists are joined with semicolons."""
        from errors import flatten_messages

        assert flatten_messages(["err1", "err2"]) == "err1; err2"

    def test_flatten_dict(self) -> None:
        """Dicts are flattened to 'key: message'."""
        from errors import flatten_messages

        assert flatten_messages({"field": ["Missing data"]}) == "field: Missing data"

    def test_flatten_nested_dict(self) -> None:
        """Nested dicts are flattened with key prefixes."""
        from errors import flatten_messages

        result = flatten_messages({"parent": {"child": ["msg"]}})
        assert "parent" in result
        assert "child" in result
        assert "msg" in result


class TestRoutingErrors:
    """Routing-level errors must return JSON, not HTML."""

    def test_no_route_404_returns_json(self, client: FlaskClient) -> None:
        """Non-matching URL returns JSON problem details."""
        resp = client.get("/does-not-exist")
        assert resp.status_code == HTTPStatus.NOT_FOUND
        assert resp.mimetype == "application/problem+json"
        data = resp.get_json()
        assert data["type"] == "about:blank"
        assert data["title"] == "Not Found"
        assert "detail" in data

    def test_wrong_method_405_returns_json(self, client: FlaskClient) -> None:
        """Wrong-method request returns JSON problem details."""
        resp = client.delete("/dash/api/")
        assert resp.status_code == HTTPStatus.METHOD_NOT_ALLOWED
        assert resp.mimetype == "application/problem+json"
        assert resp.get_json()["title"] == "Method Not Allowed"


class TestAuthoredErrors:
    """Authored HTTPExceptions return the correct shape."""

    def test_not_found_from_get_or_404(self, client: FlaskClient) -> None:
        """get_or_404 raises NotFound → problem details with 404."""
        resp = client.get("/dash/api/experiments/nonexistent")
        assert resp.status_code == HTTPStatus.NOT_FOUND
        data = resp.get_json()
        assert data["type"] == "about:blank"
        assert data["title"] == "Not Found"
        assert "nonexistent" in data["detail"]

    def test_validation_error_returns_400(self, app: Flask, client: FlaskClient) -> None:
        """ValidationError is converted to a 400 problem-details response."""

        @app.route("/_test/validation")
        def _validation() -> ResponseReturnValue:
            raise ValidationError({"field": ["Missing data"]})

        resp = client.get("/_test/validation")
        assert resp.status_code == HTTPStatus.BAD_REQUEST
        data = resp.get_json()
        assert data["title"] == "Bad Request"
        assert "field" in data["detail"]
        assert "Missing data" in data["detail"]

    def test_bad_request_from_route(self, app: Flask, client: FlaskClient) -> None:
        """Explicit BadRequest returns the authored detail."""

        @app.route("/_test/bad-request")
        def _bad_request() -> ResponseReturnValue:
            from werkzeug.exceptions import BadRequest

            raise BadRequest("Custom bad request message")

        resp = client.get("/_test/bad-request")
        assert resp.status_code == HTTPStatus.BAD_REQUEST
        data = resp.get_json()
        assert data["title"] == "Bad Request"
        assert data["detail"] == "Custom bad request message"


class TestUnhandledExceptions:
    """Unexpected exceptions must return generic detail, never str(e)."""

    def test_unhandled_returns_generic_detail(self, app: Flask, client: FlaskClient) -> None:
        """RuntimeError message must not leak into the client response."""

        @app.route("/_test/unhandled")
        def _unhandled() -> ResponseReturnValue:
            raise RuntimeError("internal secret detail with /path/to/file")

        resp = client.get("/_test/unhandled")
        assert resp.status_code == HTTPStatus.INTERNAL_SERVER_ERROR
        data = resp.get_json()
        assert data["title"] == "Internal Server Error"
        assert data["type"] == "about:blank"
        assert "internal secret detail" not in data["detail"]
        assert "/path/to/file" not in data["detail"]

    def test_unhandled_returns_problem_content_type(self, app: Flask, client: FlaskClient) -> None:
        """Unexpected exceptions return application/problem+json."""

        @app.route("/_test/crash")
        def _crash() -> ResponseReturnValue:
            raise ValueError("boom")

        resp = client.get("/_test/crash")
        assert resp.mimetype == "application/problem+json"

    @pytest.mark.xfail(reason="rollback verification requires DB mutation tracking")
    def test_unhandled_rolls_back_session(self, app: Flask, client: FlaskClient) -> None:
        """Uncaught exceptions call db.session.rollback()."""
        pass
