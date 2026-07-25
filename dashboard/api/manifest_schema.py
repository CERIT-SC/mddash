import json
import logging
import re
from functools import lru_cache
from pathlib import Path

from enums import Engine

logger = logging.getLogger(__name__)

_SCHEMA_DIR = Path(__file__).resolve().parent / "manifest_schemas"
_ENGINE_FILE = {Engine.GMX: "gromacs.schema.json", Engine.AMBER: "amber.schema.json"}
_SCHEMA_URL_RE = re.compile(
    r"^https://raw\.githubusercontent\.com/CERIT-SC/mddash/.+/dashboard/api/manifest_schemas/(gromacs|amber)\.schema\.json$"
)


def schema_url(engine: Engine) -> str:
    """Build the schema URL the API writes into manifests."""
    return f"https://raw.githubusercontent.com/CERIT-SC/mddash/v0.1.4/dashboard/api/manifest_schemas/{_ENGINE_FILE[engine]}"


@lru_cache(maxsize=2)
def _bundled(filename: str) -> dict | None:
    try:
        return json.loads((_SCHEMA_DIR / filename).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        logger.error("Failed to load bundled schema: %s", filename)
        return None


def resolve_schema_url(ref: object) -> dict | None:
    """Resolve a $schema URL to the bundled schema (any ref); None if unrecognized."""
    if not isinstance(ref, str):
        return None
    match = _SCHEMA_URL_RE.match(ref)
    return _bundled(f"{match.group(1)}.schema.json") if match else None
