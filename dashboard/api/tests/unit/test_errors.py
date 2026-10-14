"""Tests for RFC 9457 problem-details error handling."""

from http import HTTPStatus

import pytest
from dependencies import SessionDep
from errors import ApiError, BadRequest, flatten_validation
from fastapi import FastAPI
from httpx import AsyncClient
from models import Experiment
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


class TestProblemResponse:
    """Tests for ApiError.to_response() and flatten_validation()."""

    def test_api_error_renders_problem_response(self) -> None:
        """ApiError.to_response() returns correct status, media type, and body fields."""
        resp = ApiError(HTTPStatus.NOT_FOUND, "Resource missing", "urn:mddash:not-found").to_response()
        assert resp.status_code == 404
        assert resp.media_type == "application/problem+json"
        assert resp.body == b'{"type":"urn:mddash:not-found","title":"Not Found","detail":"Resource missing"}'

    def test_api_error_includes_solution(self) -> None:
        """ApiError.to_response() emits a `solution` member when provided."""
        resp = ApiError(
            HTTPStatus.CONFLICT,
            "Notebook pod already exists.",
            "urn:mddash:notebook-already-exists",
            "Open it instead.",
        ).to_response()
        assert b'"solution":"Open it instead."' in resp.body

    def test_api_error_no_status_in_body(self) -> None:
        """Status code must not appear in the JSON body."""
        resp = ApiError(HTTPStatus.INTERNAL_SERVER_ERROR, "msg", "urn:mddash:internal-error").to_response()
        assert b"status" not in resp.body

    def test_status_errors_derive_their_token(self) -> None:
        """BadRequest/NotFound/... keep the status-name token and the authored detail."""
        err = BadRequest("Custom bad request message")
        assert err.status_code == HTTPStatus.BAD_REQUEST
        assert err.problem_type == "urn:mddash:bad-request"
        assert err.description == "Custom bad request message"

    def test_flatten_validation_joins_locations(self) -> None:
        """Locations drop the body/query prefix and are joined with semicolons."""
        errors = [
            {"loc": ("body", "np"), "msg": "Field required"},
            {"loc": ("query", "tail"), "msg": "Input should be greater than or equal to 1"},
            {"loc": (), "msg": "Bare message"},
        ]
        assert flatten_validation(errors) == (
            "np: Field required; tail: Input should be greater than or equal to 1; Bare message"
        )


class TestRoutingErrors:
    """Routing-level errors must return JSON, not HTML."""

    async def test_no_route_404_returns_json(self, client: AsyncClient) -> None:
        """Non-matching URL returns JSON problem details."""
        resp = await client.get("/does-not-exist")
        assert resp.status_code == HTTPStatus.NOT_FOUND
        assert resp.headers["content-type"] == "application/problem+json"
        data = resp.json()
        assert data["type"] == "urn:mddash:not-found"
        assert data["title"] == "Not Found"
        assert "detail" in data
        assert "solution" not in data  # routing 404 has no value-add solution

    async def test_wrong_method_405_returns_json(self, client: AsyncClient) -> None:
        """Wrong-method request returns JSON problem details."""
        resp = await client.delete("/dash/api/")
        assert resp.status_code == HTTPStatus.METHOD_NOT_ALLOWED
        assert resp.headers["content-type"] == "application/problem+json"
        data = resp.json()
        assert data["title"] == "Method Not Allowed"
        assert data["type"] == "urn:mddash:method-not-allowed"


class _Body(BaseModel):
    field: int


class TestAuthoredErrors:
    """Authored errors return the correct shape."""

    async def test_not_found_for_missing_experiment(self, client: AsyncClient) -> None:
        """A missing experiment raises NotFound → problem details with 404."""
        resp = await client.get("/dash/api/experiments/nonexistent")
        assert resp.status_code == HTTPStatus.NOT_FOUND
        data = resp.json()
        assert data["type"] == "urn:mddash:not-found"
        assert data["title"] == "Not Found"
        assert "nonexistent" in data["detail"]

    async def test_validation_error_returns_400(self, app: FastAPI, client: AsyncClient) -> None:
        """Request validation errors are converted to a 400 problem-details response."""

        @app.post("/_test/validation")
        async def _validation(body: _Body) -> int:
            return body.field

        resp = await client.post("/_test/validation", json={})
        assert resp.status_code == HTTPStatus.BAD_REQUEST
        data = resp.json()
        assert data["title"] == "Bad Request"
        assert data["type"] == "urn:mddash:validation-error"
        assert "solution" not in data  # validation has no solution (detail implies the fix)
        assert "field" in data["detail"]
        assert "Field required" in data["detail"]

    async def test_bad_request_from_route(self, app: FastAPI, client: AsyncClient) -> None:
        """Explicit BadRequest returns the authored detail."""

        @app.get("/_test/bad-request")
        async def _bad_request() -> None:
            raise BadRequest("Custom bad request message")

        resp = await client.get("/_test/bad-request")
        assert resp.status_code == HTTPStatus.BAD_REQUEST
        data = resp.json()
        assert data["title"] == "Bad Request"
        assert data["type"] == "urn:mddash:bad-request"  # ad-hoc BadRequest → status-based default
        assert data["detail"] == "Custom bad request message"

    async def test_value_add_token_returns_type_and_solution(self, app: FastAPI, client: AsyncClient) -> None:
        """An ApiError carries its type token + solution through to the response."""

        @app.get("/_test/value-add")
        async def _value_add() -> None:
            raise ApiError(
                HTTPStatus.CONFLICT,
                "Notebook pod already exists.",
                "urn:mddash:notebook-already-exists",
                "The notebook is already running; open it instead.",
            )

        resp = await client.get("/_test/value-add")
        assert resp.status_code == HTTPStatus.CONFLICT
        data = resp.json()
        assert data["type"] == "urn:mddash:notebook-already-exists"
        assert data["solution"] == "The notebook is already running; open it instead."


class TestUnhandledExceptions:
    """Unexpected exceptions must return generic detail, never str(e)."""

    async def test_unhandled_returns_generic_detail(self, app: FastAPI, client: AsyncClient) -> None:
        """RuntimeError message must not leak into the client response."""

        @app.get("/_test/unhandled")
        async def _unhandled() -> None:
            raise RuntimeError("internal secret detail with /path/to/file")

        resp = await client.get("/_test/unhandled")
        assert resp.status_code == HTTPStatus.INTERNAL_SERVER_ERROR
        assert resp.headers["content-type"] == "application/problem+json"
        data = resp.json()
        assert data["title"] == "Internal Server Error"
        assert data["type"] == "urn:mddash:internal-error"
        assert data["solution"]  # retry/support guidance present
        assert "instance" not in data  # no correlation-ID field
        assert "internal secret detail" not in data["detail"]
        assert "/path/to/file" not in data["detail"]

    @pytest.mark.parametrize("exc", [ValueError("boom"), KeyError("boom")])
    async def test_unhandled_discards_uncommitted_work(
        self, app: FastAPI, client: AsyncClient, db_session: AsyncSession, exc: Exception
    ) -> None:
        """A request failing mid-way leaves no uncommitted rows behind."""

        @app.post("/_test/crash")
        async def _crash(session: SessionDep) -> None:
            session.add(Experiment(id="crash", name="never stored"))
            await session.flush()
            raise exc

        resp = await client.post("/_test/crash")
        assert resp.status_code == HTTPStatus.INTERNAL_SERVER_ERROR
        assert (await db_session.execute(select(Experiment).filter_by(id="crash"))).first() is None
