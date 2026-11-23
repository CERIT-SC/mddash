"""Discovery pins: the expected steps are shared with the TS tracker (`src/discovery.ts`)."""

import json
from pathlib import Path

import pytest
from jupyterlab_pipeline_tracker.discovery import discover_steps

ROOT = Path(__file__).resolve().parents[1]
EXPECTED = json.loads((ROOT / "tests" / "discovery_expected.json").read_text())


@pytest.mark.parametrize("name", sorted(EXPECTED))
def test_discovers_the_pinned_steps(name: str) -> None:
    notebook = json.loads((ROOT / "test-notebooks" / name).read_text())

    steps = [{"label": s.label, "source": s.source, "cells": s.cell_indices} for s in discover_steps(notebook)]

    assert steps == EXPECTED[name]
