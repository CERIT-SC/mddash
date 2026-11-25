"""The headless executor: status doc transitions, saved outputs, and failure capture."""

import json
import os
import shutil
from pathlib import Path

import nbformat
import pytest
from jupyterlab_pipeline_tracker.run import main

NOTEBOOKS = Path(__file__).resolve().parents[1] / "test-notebooks"


def _run(tmp_path: Path, notebook: Path) -> tuple[int, dict]:
    shutil.copy(notebook, tmp_path / "setup.ipynb")
    code = main(["setup.ipynb", "--status", ".setup.json", "--root", str(tmp_path)])
    return code, json.loads((tmp_path / ".setup.json").read_text())


def test_a_clean_run_ends_done_at_the_last_step(tmp_path: Path) -> None:
    code, status = _run(tmp_path, NOTEBOOKS / "01-heading-discovery.ipynb")

    assert code == 0
    assert status["state"] == "done"
    assert (status["step"], status["total"], status["title"]) == (3, 3, "Analysis")
    assert status["error"] is None
    assert status["finished_at"] is not None


def test_a_failing_cell_stops_the_run_and_keeps_its_outputs(tmp_path: Path) -> None:
    code, status = _run(tmp_path, NOTEBOOKS / "05-fallback-and-failure.ipynb")

    assert code == 1
    assert status["state"] == "failed"
    assert (status["step"], status["total"]) == (2, 3)
    assert status["error"] == {
        "step": 2,
        "cell": 2,
        "ename": "RuntimeError",
        "evalue": "Intentional failure for tracker validation",
    }
    saved = nbformat.read(tmp_path / "setup.ipynb", as_version=4)
    assert saved.cells[1].outputs[0]["text"] == "First fallback step succeeded\n"
    assert saved.cells[2].outputs[0]["ename"] == "RuntimeError"
    assert saved.cells[3].outputs == []


def test_records_the_manifests_the_run_writes(tmp_path: Path) -> None:
    notebook = nbformat.v4.new_notebook(
        cells=[
            nbformat.v4.new_markdown_cell("## Write manifest"),
            nbformat.v4.new_code_cell(
                "from pathlib import Path\nPath('md').mkdir()\nPath('md/protein.simulation.json').write_text('{}')"
            ),
        ]
    )
    (tmp_path / "old.simulation.json").write_text("{}")
    source = tmp_path / "source.ipynb"
    nbformat.write(notebook, source)
    os.utime(tmp_path / "old.simulation.json", (0, 0))

    code, status = _run(tmp_path, source)

    assert code == 0
    assert status["manifests"] == ["md/protein.simulation.json"]


@pytest.mark.parametrize("name", ["02-marker-discovery-no-headings.ipynb", "03-metadata-discovery.ipynb"])
def test_reports_every_discovered_step(tmp_path: Path, name: str) -> None:
    code, status = _run(tmp_path, NOTEBOOKS / name)

    assert code == 0
    assert status["step"] == status["total"] == 3
