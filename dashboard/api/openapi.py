"""
OpenAPI document generation (the UI client is generated from the committed `openapi.yaml`).

Run `python openapi.py` to rewrite `openapi.yaml` from the routes and schemas,
`python openapi.py --check` to fail when the committed file is stale.
"""

import argparse
import os
import re
import sys
import tempfile
from pathlib import Path
from typing import Any

import yaml
from fastapi import FastAPI
from fastapi.openapi.utils import get_openapi
from pydantic import TypeAdapter
from schemas.common import Problem

CONTRACT_PATH = Path(__file__).parent / "openapi.yaml"

TAGS = ["System", "Experiments", "Simulations", "GROMACS", "AMBER", "Tuner", "Analysis", "Notebooks", "Files", "MDRepo"]

_REF_TEMPLATE = "#/components/schemas/{model}"
# Docstring sections are for Python readers; operation descriptions keep the summary prose.
_DOCSTRING_SECTIONS = re.compile(r"\n\n(?:Args|Returns|Raises|Yields):.*", re.DOTALL)
# FastAPI names multipart bodies after the operation; the client keeps the contract name.
_BODY_RENAMES = {"Body_createExperiment": "CreateExperimentForm"}


def _walk(node: Any, visit: Any) -> Any:  # ruff:ignore[any-type]
    if isinstance(node, dict):
        return visit({key: _walk(value, visit) for key, value in node.items()})
    if isinstance(node, list):
        return [_walk(item, visit) for item in node]
    return node


def _strip_noise(node: dict) -> dict:
    """Drop generated property titles; a `title` mapping to a schema is a property named title and stays."""
    return {key: value for key, value in node.items() if not (key == "title" and isinstance(value, str))}


def _refs(node: Any) -> set[str]:  # ruff:ignore[any-type]
    found: set[str] = set()

    def visit(item: dict) -> dict:
        if isinstance(ref := item.get("$ref"), str):
            found.add(ref.rsplit("/", 1)[-1])
        return item

    _walk(node, visit)
    return found


def _component_renames(components: dict[str, Any]) -> dict[str, str]:
    """Contract names for generated ones: multipart bodies, and module-qualified names whose short name is free."""
    renames: dict[str, str] = {}
    for name in components:
        for prefix, target in _BODY_RENAMES.items():
            if name.startswith(prefix):
                renames[name] = target
        short = name.rsplit("__", 1)[-1]
        if short != name and short not in components:
            renames[name] = short
    return renames


def _prune(schema: dict[str, Any]) -> None:
    """Drop components nothing references (enums only used through inline enum schemas)."""
    components = schema["components"]["schemas"]
    reachable = _refs(schema["paths"])
    pending = set(reachable)
    while pending:
        name = pending.pop()
        for ref in _refs(components.get(name, {})) - reachable:
            reachable.add(ref)
            pending.add(ref)
    for name in set(components) - reachable:
        del components[name]


def _tidy_operation(operation: dict[str, Any]) -> None:
    if "description" in operation:
        operation["description"] = _DOCSTRING_SECTIONS.sub("", operation["description"]).strip()
    responses = operation.get("responses", {})
    # Validation errors are rendered as 400 problem details, never as FastAPI's 422 body.
    if "HTTPValidationError" in str(responses.get("422", {})):
        del responses["422"]
    # Routes returning explicit responses get an untyped placeholder 200 from FastAPI.
    placeholder = responses.get("200", {})
    if (
        placeholder.get("description") == "Successful Response"
        and placeholder.get("content", {}).get("application/json", {}).get("schema") == {}
    ):
        del responses["200"]
    # An optional body is simply omitted; `null` is no valid body.
    for media in operation.get("requestBody", {}).get("content", {}).values():
        variants = media.get("schema", {}).get("anyOf", [])
        if len(variants) == 2 and {"type": "null"} in variants:  # ruff:ignore[magic-value-comparison]
            media["schema"] = next(v for v in variants if v != {"type": "null"})


def build_openapi(app: FastAPI) -> dict[str, Any]:
    """Build the OpenAPI 3.1 document of `app` with problem-details errors instead of FastAPI's 422 shapes."""
    schema = get_openapi(
        title=app.title,
        version=app.version,
        description=app.description,
        routes=app.routes,
        servers=[{"url": "/"}],
        tags=[{"name": tag} for tag in TAGS],
        separate_input_output_schemas=app.separate_input_output_schemas,
    )
    schema["jsonSchemaDialect"] = "https://json-schema.org/draft/2020-12/schema"

    components: dict[str, Any] = schema.setdefault("components", {}).setdefault("schemas", {})
    for path_item in schema["paths"].values():
        for operation in path_item.values():
            _tidy_operation(operation)
    components.pop("HTTPValidationError", None)
    components.pop("ValidationError", None)

    components["Problem"] = TypeAdapter(Problem).json_schema(ref_template=_REF_TEMPLATE)
    _prune(schema)

    renames = _component_renames(components)
    for old, new in renames.items():
        components[new] = components.pop(old)

    def rename_ref(node: dict) -> dict:
        ref = node.get("$ref")
        if isinstance(ref, str) and (name := ref.rsplit("/", 1)[-1]) in renames:
            return {**node, "$ref": _REF_TEMPLATE.format(model=renames[name])}
        return node

    schema = _walk(schema, rename_ref)
    schema["components"]["schemas"] = _walk(schema["components"]["schemas"], _strip_noise)
    schema["paths"] = _walk(schema["paths"], _strip_noise)
    schema["components"]["schemas"] = dict(sorted(schema["components"]["schemas"].items()))
    return schema


def install_openapi(app: FastAPI) -> None:
    """Serve the post-processed document at the app's `openapi_url`."""

    def openapi() -> dict[str, Any]:
        if app.openapi_schema is None:
            app.openapi_schema = build_openapi(app)
        return app.openapi_schema

    app.openapi = openapi  # ty: ignore[invalid-assignment]


def render(schema: dict[str, Any]) -> str:
    """Render the committed YAML form of the document."""
    return yaml.safe_dump(schema, sort_keys=False, allow_unicode=True, width=120)


def main() -> int:
    """Write (or with --check, verify) the committed contract."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="fail if openapi.yaml is out of date")
    args = parser.parse_args()

    # Contract paths are the un-prefixed `/dash/api/...`; config reads these at import.
    os.environ["JUPYTERHUB_SERVICE_PREFIX"] = "/"
    os.environ.setdefault("NS_MAX_NOTEBOOKS", "1")
    os.environ.setdefault("LOG_LEVEL", "ERROR")
    os.environ.setdefault("DATA_DIR", tempfile.mkdtemp(prefix="mddash-openapi-"))
    from app import create_app  # ruff:ignore[import-outside-top-level]  # config must see the env above

    rendered = render(build_openapi(create_app()))
    if args.check:
        if CONTRACT_PATH.read_text(encoding="utf-8") != rendered:
            print(f"{CONTRACT_PATH.name} is out of date; run `make openapi`.", file=sys.stderr)
            return 1
        return 0
    CONTRACT_PATH.write_text(rendered, encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
