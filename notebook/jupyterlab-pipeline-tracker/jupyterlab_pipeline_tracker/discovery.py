"""
Pipeline step discovery: a port of `src/discovery.ts` for the headless executor.

Keep the two in lockstep; `tests/discovery_expected.json` pins both against `test-notebooks/`.
"""

import re
from dataclasses import dataclass, field
from typing import Any, Literal

type StepSource = Literal["metadata", "cell-metadata", "marker", "heading", "explicit", "fallback"]

_MARKER = re.compile(r"^(?:\s*(?:#|//)\s*)?(?:<!--\s*)?pipeline[-_\s]?step\s*:\s*(.+?)(?:\s*-->)?\s*$", re.IGNORECASE)
_EXPLICIT = re.compile(r"""tracker\s*\.\s*step\s*\(\s*['"]([^'"]+)['"]""")
_HEADING = re.compile(r"^#+\s*(.+)$")
_FALLBACK_LABEL_MAX = 48
_LINES = re.compile(r"\r?\n")


@dataclass
class Step:
    """A discovered pipeline step and the code cells it runs."""

    label: str
    source: StepSource
    cell_indices: list[int] = field(default_factory=list)


@dataclass
class _ParsedMetadataStep:
    label: str
    cells: list[int] | None = None
    start: int | None = None
    end: int | None = None


def _cell_source(cell: dict[str, Any]) -> str:
    source = cell.get("source", "")
    return "".join(source) if isinstance(source, list) else str(source)


def _index(value: object) -> int | None:
    """Return a non-negative integer as `numberFromMetadata` accepts it (bools excluded), else None."""
    return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else None


def _extract_heading(markdown: str) -> str | None:
    last = None
    for line in _LINES.split(markdown):
        if match := _HEADING.match(line.strip()):
            last = match.group(1).strip()
    return last


def _pipeline_markers(source: str) -> list[str]:
    labels = []
    for line in _LINES.split(source):
        if (match := _MARKER.match(line)) and (label := match.group(1).strip()):
            labels.append(label)
    return labels


def _explicit_steps(source: str) -> list[str]:
    return _EXPLICIT.findall(source)


def _is_tracker_bootstrap(source: str) -> bool:
    return "from pipeline_tracker" in source and "PipelineTracker" in source


def _runnable(cell: dict[str, Any]) -> bool:
    source = _cell_source(cell)
    return cell.get("cell_type") == "code" and bool(source.strip()) and not _is_tracker_bootstrap(source)


def _label_of(raw: dict[str, Any]) -> object:
    for key in ("label", "title", "name"):
        if key in raw and raw[key] is not None:
            return raw[key]
    return None


def _first_index(raw: dict[str, Any], *keys: str) -> int | None:
    for key in keys:
        if (value := _index(raw.get(key))) is not None:
            return value
    return None


def _parse_metadata_step(raw: object, fallback_start: int | None) -> _ParsedMetadataStep | None:
    if isinstance(raw, str):
        return _ParsedMetadataStep(raw.strip(), start=fallback_start) if raw.strip() else None
    if not isinstance(raw, dict):
        return None
    label = _label_of(raw)
    if not isinstance(label, str) or not label.strip():
        return None
    cells = raw.get("cells")
    start = _first_index(raw, "start_cell", "startCell", "start", "cell", "cell_index", "cellIndex")
    return _ParsedMetadataStep(
        label=label.strip(),
        cells=[c for c in cells if _index(c) is not None] if isinstance(cells, list) else None,
        start=fallback_start if start is None else start,
        end=_first_index(raw, "end_cell", "endCell", "end"),
    )


def _cell_metadata_labels(cell: dict[str, Any]) -> list[str]:
    metadata = cell.get("metadata") or {}
    raw = None
    for key in ("pipeline_step", "pipelineTrackerStep", "pipeline_tracker_step"):
        if metadata.get(key) is not None:
            raw = metadata[key]
            break
    if isinstance(raw, str) and raw.strip():
        return [raw.strip()]
    if isinstance(raw, list):
        return [value.strip() for value in raw if isinstance(value, str) and value.strip()]
    if isinstance(raw, dict):
        label = _label_of(raw)
        return [label.strip()] if isinstance(label, str) and label.strip() else []
    return []


def _metadata_steps(notebook: dict[str, Any], cells: list[dict[str, Any]]) -> list[Step]:
    metadata = notebook.get("metadata") or {}
    raw = metadata.get("pipeline_tracker")
    if raw is None:
        raw = metadata.get("pipelineTracker")
    raw_steps = raw if isinstance(raw, list) else raw.get("steps") if isinstance(raw, dict) else None
    if not isinstance(raw_steps, list):
        return []

    code_cells = [index for index, cell in enumerate(cells) if _runnable(cell)]
    parsed_steps = [
        parsed
        for index, step in enumerate(raw_steps)
        if (parsed := _parse_metadata_step(step, code_cells[index] if index < len(code_cells) else None))
    ]

    steps = []
    for index, parsed in enumerate(parsed_steps):
        explicit = [c for c in parsed.cells if c in code_cells] if parsed.cells is not None else None
        next_start = next((s.start for s in parsed_steps[index + 1 :] if s.start is not None), None)
        end = parsed.end if parsed.end is not None else (next_start - 1 if next_start is not None else len(cells) - 1)
        if explicit:
            indices = explicit
        elif parsed.start is not None:
            indices = [i for i in range(parsed.start, min(end, len(cells) - 1) + 1) if _runnable(cells[i])]
        else:
            indices = []
        if not indices and parsed.start is not None and parsed.start in code_cells:
            indices = [parsed.start]
        if indices:
            steps.append(Step(parsed.label, "metadata", indices))
    return steps


def _fallback_label(source: str, index: int) -> str:
    first = next((line.strip() for line in _LINES.split(source) if line.strip()), "")
    if not first:
        return f"Code cell {index + 1}"
    text = re.sub(r"^#\s*", "", first).strip()
    return (
        f"Code cell {index + 1}: {text[: _FALLBACK_LABEL_MAX - 3] + '...' if len(text) > _FALLBACK_LABEL_MAX else text}"
    )


def discover_steps(notebook: dict[str, Any]) -> list[Step]:
    """Discover the notebook's (nbformat JSON) steps in the JupyterLab tracker's order and grouping."""
    cells: list[dict[str, Any]] = notebook.get("cells") or []
    if metadata_steps := _metadata_steps(notebook, cells):
        return metadata_steps

    steps: list[Step] = []
    current_heading: str | None = None
    current_source: StepSource = "heading"
    heading_step: Step | None = None

    for index, cell in enumerate(cells):
        kind = cell.get("cell_type")
        source = _cell_source(cell)

        if kind == "markdown":
            if markers := _pipeline_markers(source):
                current_heading, current_source, heading_step = markers[-1], "marker", None
            elif heading := _extract_heading(source):
                current_heading, current_source, heading_step = heading, "heading", None
            continue

        if not _runnable(cell):
            continue

        metadata_labels = _cell_metadata_labels(cell)
        marker_labels = _pipeline_markers(source)
        explicit_labels = [*metadata_labels, *marker_labels, *_explicit_steps(source)]
        if explicit_labels:
            for label in explicit_labels:
                kind_of: StepSource = (
                    "cell-metadata" if label in metadata_labels else "marker" if label in marker_labels else "explicit"
                )
                steps.append(Step(label, kind_of, [index]))
            heading_step = None
            continue

        if current_heading is None:
            continue
        if heading_step is None:
            heading_step = Step(current_heading, current_source, [index])
            steps.append(heading_step)
        else:
            heading_step.cell_indices.append(index)

    if steps:
        return steps
    return [
        Step(_fallback_label(_cell_source(cell), index), "fallback", [index])
        for index, cell in enumerate(cells)
        if _runnable(cell)
    ]
