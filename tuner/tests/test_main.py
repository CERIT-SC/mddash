from api.main import app
from fastapi.testclient import TestClient

AUTH = ("test-user", "test-password")
MAX_REQUEST_SIZE = 10 * 1024**3


def test_openapi_schema_is_generated_under_api_prefix() -> None:
    response = TestClient(app).get("/api/openapi.json")

    assert response.status_code == 200
    schema = response.json()
    assert schema["info"]["title"] == "MD Tuner API"
    assert "/api/tuning-jobs/gmx" in schema["paths"]
    assert "/api/tuning-jobs/amber" in schema["paths"]


def test_unauthenticated_oversized_request_is_rejected_before_parsing() -> None:
    response = TestClient(app).post(
        "/api/tuning-jobs/gmx",
        headers={"content-length": str(MAX_REQUEST_SIZE + 1)},
    )

    assert response.status_code == 413


def test_oversized_request_is_rejected_before_multipart_parsing() -> None:
    response = TestClient(app).post(
        "/api/tuning-jobs/gmx",
        headers={"content-length": str(MAX_REQUEST_SIZE + 1)},
        auth=AUTH,
    )

    assert response.status_code == 413
