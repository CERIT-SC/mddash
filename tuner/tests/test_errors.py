import json
from http import HTTPStatus

from api.errors import ApiError, register_exception_handlers
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient


def _make_app() -> FastAPI:
    app = FastAPI()
    register_exception_handlers(app)

    @app.get("/_test/not-found")
    def _raise_not_found() -> None:
        raise HTTPException(status_code=404, detail="Resource missing")

    @app.get("/_test/api-error")
    def _raise_api_error() -> None:
        raise ApiError(
            HTTPStatus.SERVICE_UNAVAILABLE,
            "Tuner is unavailable.",
            "urn:mddash:upstream-unavailable",
            "Try again in a moment.",
        )

    @app.get("/_test/unhandled")
    def _raise_unhandled() -> None:
        raise RuntimeError("internal secret detail with /path/to/file")

    @app.get("/_test/validation")
    def _validation(n: int) -> dict:
        return {"n": n}

    return app


class TestApiErrorRender:
    def test_renders_problem_response(self) -> None:
        resp = ApiError(HTTPStatus.NOT_FOUND, "Resource missing", "urn:mddash:not-found").to_response()
        assert resp.status_code == 404
        assert resp.media_type == "application/problem+json"
        data = json.loads(resp.body)
        assert data["type"] == "urn:mddash:not-found"
        assert data["title"] == "Not Found"
        assert data["detail"] == "Resource missing"

    def test_includes_solution(self) -> None:
        resp = ApiError(
            HTTPStatus.INTERNAL_SERVER_ERROR, "boom", "urn:mddash:internal-error", "Try again."
        ).to_response()
        data = json.loads(resp.body)
        assert data["solution"] == "Try again."

    def test_no_status_in_body(self) -> None:
        resp = ApiError(HTTPStatus.INTERNAL_SERVER_ERROR, "msg", "urn:mddash:internal-error").to_response()
        assert "status" not in json.loads(resp.body)


class TestRoutingErrors:
    def test_no_route_404_returns_problem(self) -> None:
        client = TestClient(_make_app(), raise_server_exceptions=False)
        resp = client.get("/does-not-exist")
        assert resp.status_code == HTTPStatus.NOT_FOUND
        assert resp.headers["content-type"].startswith("application/problem+json")
        data = resp.json()
        assert data["type"] == "urn:mddash:not-found"
        assert data["title"] == "Not Found"
        assert "detail" in data


class TestAuthoredErrors:
    def test_http_exception_returns_problem(self) -> None:
        client = TestClient(_make_app())
        resp = client.get("/_test/not-found")
        assert resp.status_code == HTTPStatus.NOT_FOUND
        data = resp.json()
        assert data["type"] == "urn:mddash:not-found"
        assert data["title"] == "Not Found"
        assert data["detail"] == "Resource missing"

    def test_api_error_carries_solution(self) -> None:
        client = TestClient(_make_app())
        resp = client.get("/_test/api-error")
        assert resp.status_code == HTTPStatus.SERVICE_UNAVAILABLE
        data = resp.json()
        assert data["type"] == "urn:mddash:upstream-unavailable"
        assert data["solution"] == "Try again in a moment."


class TestValidationErrors:
    def test_validation_returns_400_problem(self) -> None:
        client = TestClient(_make_app())
        resp = client.get("/_test/validation")
        assert resp.status_code == HTTPStatus.BAD_REQUEST
        assert resp.headers["content-type"].startswith("application/problem+json")
        data = resp.json()
        assert data["type"] == "urn:mddash:validation-error"
        assert data["title"] == "Bad Request"
        assert "n" in data["detail"]
        assert "solution" not in data


class TestUnhandledExceptions:
    def test_unhandled_returns_generic_detail(self) -> None:
        client = TestClient(_make_app(), raise_server_exceptions=False)
        resp = client.get("/_test/unhandled")
        assert resp.status_code == HTTPStatus.INTERNAL_SERVER_ERROR
        assert resp.headers["content-type"].startswith("application/problem+json")
        data = resp.json()
        assert data["title"] == "Internal Server Error"
        assert data["type"] == "urn:mddash:internal-error"
        assert data["solution"]
        assert "internal secret detail" not in data["detail"]
        assert "/path/to/file" not in data["detail"]


class TestMiddlewarePayloadTooLarge:
    def test_oversized_request_is_problem(self) -> None:
        from api.config import MAX_REQUEST_SIZE
        from api.main import app

        client = TestClient(app)
        resp = client.post(
            "/api/tuning-jobs/gmx",
            headers={"content-length": str(MAX_REQUEST_SIZE + 1)},
            auth=("test-user", "test-password"),
        )
        assert resp.status_code == HTTPStatus.REQUEST_ENTITY_TOO_LARGE
        assert resp.headers["content-type"].startswith("application/problem+json")
        data = resp.json()
        assert data["type"] == "urn:mddash:payload-too-large"
        assert data["title"] == HTTPStatus.REQUEST_ENTITY_TOO_LARGE.phrase
        assert "detail" in data
