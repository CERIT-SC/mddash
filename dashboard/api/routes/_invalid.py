"""Hand-written problems for request validation failures, keeping the API's established messages."""

from collections.abc import Iterable
from enum import Enum

from enums import AnalysisType, NotebookTier, PreprocessingMode
from errors import ApiError, BadRequest, InvalidRequest, NotFound, validation_problem

_LOCATIONS = {"body", "query", "path", "form"}
_NOT_INTEGER = {"int_parsing", "int_type", "int_from_float"}


def _field(error: dict) -> str:
    """Name the request field an error is about ("" for the body as a whole)."""
    names = [str(part) for part in error.get("loc", ()) if part not in _LOCATIONS]
    return names[0] if names else ""


def _errors_for(errors: Iterable[dict], field: str) -> list[dict]:
    return [error for error in errors if _field(error) == field]


def tail_lines(max_value: int) -> InvalidRequest:
    """Log `tail` query parameter messages."""

    def render(errors: list[dict]) -> ApiError:
        for error in _errors_for(errors, "tail"):
            raw = str(error.get("input", ""))
            if not raw.isdigit():
                return BadRequest("Tail lines must be a positive integer.")
            if int(raw) <= 0:
                return BadRequest("Tail lines must be greater than 0.")
            return BadRequest(f"Tail lines must not exceed {max_value}.")
        return validation_problem(errors)

    return render


def tuner_start(errors: list[dict]) -> ApiError:
    """simulation_path is checked first (404, as a missing tuner target), then nsteps."""
    if _errors_for(errors, "") or _errors_for(errors, "simulation_path"):
        return NotFound("simulation_path is required.")
    for error in _errors_for(errors, "nsteps"):
        if error["type"] == "missing":
            return BadRequest("nsteps is required.")
        if error["type"] in _NOT_INTEGER:
            return BadRequest("nsteps must be an integer.")
        return BadRequest("nsteps must be at least 1.")
    return validation_problem(errors)


def update_experiment(errors: list[dict]) -> ApiError:
    """Only the name is editable."""
    missing_body = any(e["type"] == "missing" and not _field(e) for e in errors)
    empty_body = any(_field(e) == "name" and e["type"] == "missing" and e.get("input") == {} for e in errors)
    if missing_body or empty_body:
        return BadRequest("No data provided.")
    return BadRequest("No valid fields to update.")


def create_experiment(errors: list[dict]) -> ApiError:
    """Engine errors name the engine; anything else is an invalid source."""
    for error in _errors_for(errors, "engine"):
        return BadRequest(f"Invalid engine: {error.get('input')}")
    if _errors_for(errors, "experiment-name"):
        # A missing name has always surfaced as the framework's generic bad-request text.
        return BadRequest("The browser (or proxy) sent a request that this server could not understand.")
    return BadRequest("Invalid experiment type or missing data.")


def publish(errors: list[dict]) -> ApiError:
    """Unknown targets are named."""
    for error in _errors_for(errors, "target"):
        return BadRequest(f"Unknown publish target: {error.get('input')}")
    return validation_problem(errors)


def simulation_write(errors: list[dict]) -> ApiError:
    """Require an object body whose files map roles to paths."""
    if _errors_for(errors, ""):
        return BadRequest("Request body must be a JSON object.")
    if _errors_for(errors, "files"):
        return BadRequest("'files' must map file roles to file paths.")
    return validation_problem(errors)


def required_simulation_path(errors: list[dict]) -> ApiError:
    """Analysis result lookups are scoped to a simulation."""
    if _errors_for(errors, "simulation_path"):
        return BadRequest("simulation_path query parameter is required.")
    return validation_problem(errors)


def _unknown(enum_cls: type[Enum], noun: str, listing: str = "Available") -> str:
    return f"Unknown {noun}. {listing}: {', '.join(str(member.value) for member in enum_cls)}"


def _schema_message(error: dict, enums: dict[str, str]) -> str:
    """Per-field messages in the wording of the request schemas they replace."""
    field = _field(error)
    match error["type"]:
        case "missing":
            return "Missing data for required field."
        case "extra_forbidden":
            return "Unknown field."
        case "string_too_short":
            return "Shorter than minimum length 1."
        case "bool_parsing" | "bool_type":
            return "Not a valid boolean."
        case "string_type":
            return "Not a valid string."
    return enums.get(field, str(error.get("msg", "Invalid value.")))


def _schema_problem(errors: list[dict], enums: dict[str, str]) -> ApiError:
    if _errors_for(errors, ""):
        return validation_problem(errors, "_schema: Invalid input type.")
    detail = "; ".join(f"{_field(error)}: {_schema_message(error, enums)}" for error in errors)
    return validation_problem(errors, detail)


def submit_analysis(errors: list[dict]) -> ApiError:
    """Analysis job request fields."""
    return _schema_problem(
        errors,
        {
            "analysis": _unknown(AnalysisType, "analysis"),
            "preprocessing_mode": _unknown(PreprocessingMode, "preprocessing_mode"),
        },
    )


def start_notebook(errors: list[dict]) -> ApiError:
    """Notebook start options."""
    return _schema_problem(errors, {"tier": _unknown(NotebookTier, "notebook tier", "Valid tiers")})
