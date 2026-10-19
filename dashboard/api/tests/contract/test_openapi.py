"""Dashboard API OpenAPI contract tests: the committed spec is generated from the app and matches responses."""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING, Any

import jsonschema
import pytest
import yaml
from openapi import CONTRACT_PATH, build_openapi, render

if TYPE_CHECKING:
    from fastapi import FastAPI
    from httpx import AsyncClient

HTTP_METHODS = {"get", "post", "put", "patch", "delete"}


@pytest.fixture(scope="module")
def contract() -> dict[str, Any]:
    """Load the committed OpenAPI contract."""
    with CONTRACT_PATH.open(encoding="utf-8") as stream:
        loaded = yaml.safe_load(stream)
    assert isinstance(loaded, dict)
    return loaded


def _resolve_ref(contract: dict[str, Any], ref: str) -> dict[str, Any]:
    assert ref.startswith("#/"), f"Only local references are allowed: {ref}"
    value: Any = contract
    for part in ref.removeprefix("#/").split("/"):
        value = value[part.replace("~1", "/").replace("~0", "~")]
    assert isinstance(value, dict)
    return value


def _response(contract: dict[str, Any], path: str, method: str, status: int | str) -> dict[str, Any]:
    response = contract["paths"][path][method]["responses"][str(status)]
    return _resolve_ref(contract, response["$ref"]) if "$ref" in response else response


def _response_schema(contract: dict[str, Any], path: str, method: str, status: int) -> dict[str, Any]:
    return _response(contract, path, method, status)["content"]["application/json"]["schema"]


def _validate_payload(contract: dict[str, Any], schema: dict[str, Any], payload: Any) -> None:
    validator = jsonschema.validators.validator_for(contract)(contract).evolve(schema=schema)
    validator.validate(payload)


def _walk(value: Any):
    yield value
    if isinstance(value, dict):
        for child in value.values():
            yield from _walk(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk(child)


def test_committed_contract_is_generated_from_the_app(app: FastAPI) -> None:
    """openapi.yaml must be regenerated (`make openapi`) whenever routes or schemas change."""
    assert CONTRACT_PATH.read_text(encoding="utf-8") == render(build_openapi(app)), (
        "openapi.yaml is out of date; run `make openapi`"
    )


def test_contract_is_valid_openapi_31_with_unique_operation_ids(contract: dict[str, Any]) -> None:
    assert contract["openapi"].startswith("3.1.")
    assert contract["jsonSchemaDialect"] == "https://json-schema.org/draft/2020-12/schema"

    operation_ids = [
        operation["operationId"]
        for path_item in contract["paths"].values()
        for method, operation in path_item.items()
        if method in HTTP_METHODS
    ]
    assert len(operation_ids) == len(set(operation_ids)), "duplicate operationIds in openapi.yaml"

    for schema in contract["components"]["schemas"].values():
        jsonschema.Draft202012Validator.check_schema(schema)

    for node in _walk(contract):
        if isinstance(node, dict) and "$ref" in node:
            _resolve_ref(contract, node["$ref"])


def test_errors_are_documented_as_problem_details_only(contract: dict[str, Any]) -> None:
    """Validation errors are 400 problem details; FastAPI's 422 validation shape never leaks into the contract."""
    assert "HTTPValidationError" not in contract["components"]["schemas"]
    for path_item in contract["paths"].values():
        for method, operation in path_item.items():
            if method not in HTTP_METHODS:
                continue
            for status, response in operation["responses"].items():
                if status == "default" or int(status) >= 400:
                    assert set(response["content"]) == {"application/problem+json"}, (method, status)


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


async def test_health_response_matches_contract(client: AsyncClient, contract: dict[str, Any]) -> None:
    response = await client.get("/dash/api/health")
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/json"
    _validate_payload(contract, _response_schema(contract, "/dash/api/health", "get", 200), response.json())


async def test_notebook_config_response_matches_contract(client: AsyncClient, contract: dict[str, Any]) -> None:
    response = await client.get("/dash/api/notebook-config")
    assert response.status_code == 200
    _validate_payload(contract, _response_schema(contract, "/dash/api/notebook-config", "get", 200), response.json())


async def test_empty_experiment_list_response_matches_contract(client: AsyncClient, contract: dict[str, Any]) -> None:
    response = await client.get("/dash/api/experiments")
    assert response.status_code == 200
    assert response.json() == []
    _validate_payload(contract, _response_schema(contract, "/dash/api/experiments", "get", 200), response.json())


async def test_populated_experiment_list_response_matches_contract(
    client: AsyncClient, contract: dict[str, Any], db_session: Any
) -> None:
    from core.enums import AnalysisType, JobStatus, SourceType
    from modules.models import AnalysisJob, Experiment, Notebook

    experiment = Experiment(id="slice", name="Vertical slice", source_type=SourceType.PDB, source_ref="1LYZ")
    db_session.add(experiment)
    db_session.add(Notebook(experiment_id="slice"))
    # A seeded job exposes the embedded analysis_jobs shape — an empty list passes either way.
    db_session.add(
        AnalysisJob(
            id="job1",
            experiment_id="slice",
            simulation_path="run.simulation.json",
            analysis_name=AnalysisType.RMSDS,
            trajectory_file="traj.xtc",
            _last_known_status=JobStatus.FINISHED,
        )
    )
    await db_session.commit()

    response = await client.get("/dash/api/experiments")
    assert response.status_code == 200
    assert [item["id"] for item in response.json()] == ["slice"]
    _validate_payload(contract, _response_schema(contract, "/dash/api/experiments", "get", 200), response.json())


async def test_problem_response_matches_contract(client: AsyncClient, contract: dict[str, Any]) -> None:
    response = await client.get("/dash/api/experiments/missing")
    assert response.status_code == 404
    assert response.headers["content-type"] == "application/problem+json"
    schema = _response(contract, "/dash/api/experiments/{experiment_id}", "get", 404)["content"]
    _validate_payload(contract, schema["application/problem+json"]["schema"], response.json())


async def test_validation_errors_are_problem_details(client: AsyncClient, contract: dict[str, Any]) -> None:
    response = await client.get("/dash/api/experiments/abcde/analysis/results")
    assert response.status_code == 400
    body = response.json()
    assert body["type"] == "urn:mddash:validation-error"
    _validate_payload(contract, {"$ref": "#/components/schemas/Problem"}, body)


async def test_analysis_variants_response_matches_contract(
    client: AsyncClient, contract: dict[str, Any], tmp_path: Path
) -> None:
    output = tmp_path / "abcde" / "analysis" / "mwf" / "run.simulation"
    output.mkdir(parents=True)
    (output / "mda.hbonds.json").write_text('[{"analysis":"hbonds-00","name":"Protein-Water"}]')

    response = await client.get(
        "/dash/api/experiments/abcde/analysis/results/hbonds/variants",
        params={"simulation_path": "run.simulation.json"},
    )
    assert response.status_code == 200
    assert response.json() == [{"analysis": "hbonds-00", "name": "Protein-Water"}]
    _validate_payload(
        contract,
        _response_schema(
            contract, "/dash/api/experiments/{experiment_id}/analysis/results/{name}/variants", "get", 200
        ),
        response.json(),
    )


async def test_typed_analysis_result_response_matches_contract(
    client: AsyncClient, contract: dict[str, Any], tmp_path: Path
) -> None:
    output = tmp_path / "abcde" / "analysis" / "mwf" / "run.simulation"
    output.mkdir(parents=True)
    payload = {
        "start": 0,
        "step": 1,
        "data": [{"reference": "backbone", "group": "protein", "values": [0.1, 0.2]}],
    }
    (output / "mda.rmsds.json").write_text(json.dumps(payload))

    response = await client.get(
        "/dash/api/experiments/abcde/analysis/results/rmsds",
        params={"simulation_path": "run.simulation.json"},
    )
    assert response.status_code == 200
    schema = _response_schema(contract, "/dash/api/experiments/{experiment_id}/analysis/results/{name}", "get", 200)
    assert "$ref" in schema
    _validate_payload(contract, schema, response.json())
