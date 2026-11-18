"""Unit tests for the one-shot Datahugger-NG population worker (pinned binding boundary)."""

import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest
from modules.population import worker
from modules.population.downloader import DOWNLOAD_CONCURRENCY
from modules.population.receipt import read_receipt, staging_dir

OPERATION_ID = "0123456789abcdef"
ARGS = ["--operation-id", OPERATION_ID, "--experiment-id", "abcde", "--repo-url", "https://github.com/test/dataset"]


@pytest.fixture
def datahugger(monkeypatch: pytest.MonkeyPatch) -> SimpleNamespace:
    """Stand-in for the pinned `datahugger` Python bindings (no network, no native runtime)."""
    state = {"fail": False}
    calls: dict = {"resolve": [], "download": []}

    class FakeDataset:
        def download_with_validation(self, dst_dir: Path, limit: int | None = None) -> int:
            receipt = read_receipt(OPERATION_ID)
            calls["download"].append({
                "dst_dir": dst_dir,
                "limit": limit,
                "receipt_state": receipt.state if receipt else None,
            })
            if state["fail"]:
                raise RuntimeError("native detail: repository unreachable")
            (dst_dir / "files").mkdir(parents=True, exist_ok=True)
            (dst_dir / "files" / "dataset.pdb").write_text("HEADER    FAKE\nEND\n")
            (dst_dir / "info.txt").write_text("fake dataset\n")
            return 2

    def fake_resolve(url: str) -> FakeDataset:
        calls["resolve"].append(url)
        return FakeDataset()

    module = ModuleType("datahugger")
    setattr(module, "resolve", fake_resolve)
    monkeypatch.setitem(sys.modules, "datahugger", module)

    return SimpleNamespace(calls=calls, state=state)


class TestWorker:
    """The worker stages the full repository and writes an atomic terminal receipt."""

    def test_success_writes_succeeded_receipt(self, datahugger: SimpleNamespace) -> None:
        """A full download resolves the URL and writes a success receipt at the fixed concurrency."""
        assert worker.main(ARGS) == 0

        receipt = read_receipt(OPERATION_ID)
        assert receipt is not None
        assert receipt.state == "succeeded"
        assert receipt.error is None

        # The binding is driven with the approved concurrency, never its zero/unlimited default.
        assert datahugger.calls["resolve"] == ["https://github.com/test/dataset"]
        assert datahugger.calls["download"] == [
            {"dst_dir": staging_dir(OPERATION_ID), "limit": DOWNLOAD_CONCURRENCY, "receipt_state": "running"}
        ]
        assert (staging_dir(OPERATION_ID) / "files" / "dataset.pdb").is_file()

    def test_concurrency_is_fixed(self) -> None:
        """The approved download concurrency is four."""
        assert DOWNLOAD_CONCURRENCY == 4

    def test_failure_writes_sanitized_failed_receipt(self, datahugger: SimpleNamespace) -> None:
        """A native failure becomes a stable receipt message; the detail never crosses the boundary."""
        datahugger.state["fail"] = True

        assert worker.main(ARGS) == 0  # the receipt, not the exit code, is the worker's report

        receipt = read_receipt(OPERATION_ID)
        assert receipt is not None
        assert receipt.state == "failed"
        assert receipt.error == "The repository download failed."

    def test_worker_never_touches_the_experiment_dir(self, datahugger: SimpleNamespace, tmp_path: Path) -> None:
        """The worker writes only staging content and its receipt (the API owns the experiment and the DB)."""
        worker.main(ARGS)

        assert not (tmp_path / "abcde").exists()

    def test_missing_arguments_exit_nonzero(self, datahugger: SimpleNamespace) -> None:
        """Argument errors are argparse's job (exit code 2)."""
        with pytest.raises(SystemExit) as excinfo:
            worker.main(["--operation-id", OPERATION_ID])
        assert excinfo.value.code == 2
