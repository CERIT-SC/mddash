"""Dashboard API OpenAPI contract tests."""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING, Any

import jsonschema
import pytest
import yaml

if TYPE_CHECKING:
    from flask import Flask
    from flask.testing import FlaskClient

OPENAPI_PATH = Path(__file__).parents[2] / "openapi.yaml"
HTTP_METHODS = {"get", "post", "put", "patch", "delete"}


@pytest.fixture(scope="module")
def contract() -> dict[str, Any]:
    """Load the API-owned OpenAPI contract."""
    with OPENAPI_PATH.open(encoding="utf-8") as stream:
        loaded = yaml.safe_load(stream)
    assert isinstance(loaded, dict)
    return loaded


def _openapi_operations(contract: dict[str, Any]) -> set[tuple[str, str]]:
    return {
        (method.upper(), path)
        for path, path_item in contract["paths"].items()
        for method in path_item
        if method in HTTP_METHODS
    }


def _flask_operations(app: Flask) -> set[tuple[str, str]]:
    return {
        (method, rule.rule.replace("<path:", "{").replace("<", "{").replace(">", "}"))
        for rule in app.url_map.iter_rules()
        if rule.endpoint != "static"
        for method in rule.methods or set()
        if method not in {"HEAD", "OPTIONS"}
    }


def _resolve_ref(contract: dict[str, Any], ref: str) -> dict[str, Any]:
    assert ref.startswith("#/"), f"Only local references are allowed: {ref}"
    value: Any = contract
    for part in ref.removeprefix("#/").split("/"):
        value = value[part.replace("~1", "/").replace("~0", "~")]
    assert isinstance(value, dict)
    return value


def _response(contract: dict[str, Any], path: str, method: str, status: int) -> dict[str, Any]:
    response = contract["paths"][path][method]["responses"][str(status)]
    return _resolve_ref(contract, response["$ref"]) if "$ref" in response else response


def _response_schema(contract: dict[str, Any], path: str, method: str, status: int) -> dict[str, Any]:
    response = _response(contract, path, method, status)
    return response["content"]["application/json"]["schema"]


def _validate_payload(contract: dict[str, Any], schema: dict[str, Any], payload: Any) -> None:
    registry = jsonschema.validators.validator_for(contract)(contract).evolve(schema=schema)
    registry.validate(payload)


def test_flask_inventory_exactly_matches_openapi(app: Flask, contract: dict[str, Any]) -> None:
    """Every canonical Flask method/path pair is documented, and no others exist."""
    flask_operations = _flask_operations(app)
    assert len(flask_operations) == 51
    assert _openapi_operations(contract) == flask_operations


def test_contract_is_valid_openapi_31_with_unique_operation_ids(contract: dict[str, Any]) -> None:
    assert contract["openapi"].startswith("3.1.")
    assert contract["jsonSchemaDialect"] == "https://json-schema.org/draft/2020-12/schema"

    operation_ids = [
        operation["operationId"]
        for path_item in contract["paths"].values()
        for method, operation in path_item.items()
        if method in HTTP_METHODS
    ]
    assert len(operation_ids) == 51
    assert len(operation_ids) == len(set(operation_ids))

    for schema in contract["components"]["schemas"].values():
        jsonschema.Draft202012Validator.check_schema(schema)

    for node in _walk(contract):
        if isinstance(node, dict) and "$ref" in node:
            _resolve_ref(contract, node["$ref"])


def _walk(value: Any):
    yield value
    if isinstance(value, dict):
        for child in value.values():
            yield from _walk(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk(child)


@pytest.mark.parametrize(
    ("path", "method", "status", "media_type"),
    [
        ("/dash/api/health", "get", 200, "application/json"),
        ("/dash/api/notebook-config", "get", 200, "application/json"),
        ("/dash/api/experiments/{experiment_id}", "get", 404, "application/problem+json"),
        ("/dash/api/experiments/{experiment_id}/analysis/results", "get", 400, "application/problem+json"),
        ("/dash/api/experiments/{experiment_id}/files/{path}", "get", 200, "application/octet-stream"),
        ("/dash/api/experiments/{experiment_id}/analysis/{job_id}", "delete", 204, None),
    ],
)
def test_representative_statuses_and_media_types_are_declared(
    contract: dict[str, Any], path: str, method: str, status: int, media_type: str | None
) -> None:
    response = _response(contract, path, method, status)
    if media_type is None:
        assert "content" not in response
    else:
        assert media_type in response["content"]


def test_health_response_matches_contract(client: FlaskClient, contract: dict[str, Any]) -> None:
    response = client.get("/dash/api/health")
    assert response.status_code == 200
    assert response.mimetype == "application/json"
    _validate_payload(contract, _response_schema(contract, "/dash/api/health", "get", 200), response.get_json())


def test_notebook_config_response_matches_contract(client: FlaskClient, contract: dict[str, Any]) -> None:
    response = client.get("/dash/api/notebook-config")
    assert response.status_code == 200
    assert response.mimetype == "application/json"
    _validate_payload(
        contract,
        _response_schema(contract, "/dash/api/notebook-config", "get", 200),
        response.get_json(),
    )


def test_problem_response_matches_contract(client: FlaskClient, contract: dict[str, Any]) -> None:
    response = client.get("/dash/api/experiments/missing")
    assert response.status_code == 404
    assert response.mimetype == "application/problem+json"
    schema = _response(contract, "/dash/api/experiments/{experiment_id}", "get", 404)["content"]
    _validate_payload(contract, schema["application/problem+json"]["schema"], response.get_json())


def test_analysis_variants_response_matches_contract(
    client: FlaskClient, contract: dict[str, Any], tmp_path: Path
) -> None:
    output = tmp_path / "abcde" / "analysis" / "mwf" / "run.simulation"
    output.mkdir(parents=True)
    (output / "mda.hbonds.json").write_text('[{"analysis":"hbonds-00","name":"Protein-Water"}]')

    response = client.get(
        "/dash/api/experiments/abcde/analysis/results/hbonds/variants",
        query_string={"simulation_path": "run.simulation.json"},
    )
    assert response.status_code == 200
    assert response.get_json() == [{"analysis": "hbonds-00", "name": "Protein-Water"}]
    _validate_payload(
        contract,
        _response_schema(
            contract,
            "/dash/api/experiments/{experiment_id}/analysis/results/{name}/variants",
            "get",
            200,
        ),
        response.get_json(),
    )


def test_typed_analysis_result_response_matches_contract(
    client: FlaskClient, contract: dict[str, Any], tmp_path: Path
) -> None:
    output = tmp_path / "abcde" / "analysis" / "mwf" / "run.simulation"
    output.mkdir(parents=True)
    payload = {
        "start": 0,
        "step": 1,
        "data": [{"reference": "backbone", "group": "protein", "values": [0.1, 0.2]}],
    }
    (output / "mda.rmsds.json").write_text(json.dumps(payload))

    response = client.get(
        "/dash/api/experiments/abcde/analysis/results/rmsds",
        query_string={"simulation_path": "run.simulation.json"},
    )
    assert response.status_code == 200
    schema = _response_schema(contract, "/dash/api/experiments/{experiment_id}/analysis/results/{name}", "get", 200)
    assert "$ref" in schema or "oneOf" in schema
    _validate_payload(contract, schema, response.get_json())
