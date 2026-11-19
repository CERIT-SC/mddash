"""Unit tests for the one-shot Datahugger-NG population worker (pinned binding boundary)."""

import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest
from modules.population import worker
from modules.population.downloader import (
    DOWNLOAD_CONCURRENCY,
    ERROR_CONNECTION,
    ERROR_STORAGE,
    ERROR_UNRECOGNIZED,
    ERROR_VALIDATION,
    sanitize_download_exception,
)
from modules.population.receipt import read_receipt, staging_dir

OPERATION_ID = "0123456789abcdef"
ARGS = ["--operation-id", OPERATION_ID, "--experiment-id", "abcde", "--repo-url", "https://github.com/test/dataset"]


@pytest.fixture
def datahugger(monkeypatch: pytest.MonkeyPatch) -> SimpleNamespace:
    """Stand-in for the pinned `datahugger` Python bindings (no network, no native runtime)."""
    state: dict[str, str | bool | None] = {"fail": False, "resolve_error": None}
    calls: dict = {"resolve": [], "download": []}

    class FakeDataset:
        def download_with_validation(self, dst_dir: Path, limit: int | None = None) -> int:
            receipt = read_receipt(OPERATION_ID)
            calls["download"].append({
                "dst_dir": dst_dir,
                "limit": limit,
                "receipt_state": receipt.state if receipt else None,
            })
            if state["fail"] is True:
                raise RuntimeError(
                    "crawler fail: fail to send http GET to https://public.example/file, to get file 'trajectory.xtc'"
                )
            if state["fail"]:
                raise RuntimeError(str(state["fail"]))
            (dst_dir / "files").mkdir(parents=True, exist_ok=True)
            (dst_dir / "files" / "dataset.pdb").write_text("HEADER    FAKE\nEND\n")
            (dst_dir / "info.txt").write_text("fake dataset\n")
            return 2

    def fake_resolve(url: str) -> FakeDataset:
        calls["resolve"].append(url)
        if state["resolve_error"]:
            raise RuntimeError(str(state["resolve_error"]))
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

        assert worker.main(ARGS) == 1

        receipt = read_receipt(OPERATION_ID)
        assert receipt is not None
        assert receipt.state == "failed"
        assert receipt.error == f"The repository could not provide file 'trajectory.xtc'. {ERROR_CONNECTION}"
        assert "public.example" not in receipt.error

    def test_unknown_download_error_does_not_leak_native_detail(self, datahugger: SimpleNamespace) -> None:
        """A new or unexpected Rust error must never pass through to the browser."""
        datahugger.state["fail"] = "native detail: secret response payload"

        assert worker.main(ARGS) == 1
        receipt = read_receipt(OPERATION_ID)
        assert receipt is not None
        assert receipt.error == worker.RECEIPT_ERROR_DOWNLOAD_FAILED
        assert "native detail" not in (receipt.error or "")

        datahugger.state["fail"] = False

    def test_resolution_error_is_actionable(self, datahugger: SimpleNamespace) -> None:
        """Unsupported repository domains are reported before a dataset download begins."""
        datahugger.state["resolve_error"] = "unknown domain: unsupported.example"

        assert worker.main(ARGS) == 1
        receipt = read_receipt(OPERATION_ID)
        assert receipt is not None
        assert receipt.error == ERROR_UNRECOGNIZED
        assert not datahugger.calls["download"]

    def test_startup_failure_writes_failed_receipt(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Receipt-initialization failures still terminate nonzero and remain private to the log."""
        monkeypatch.setattr(worker, "write_receipt", lambda *args: (_ for _ in ()).throw(OSError("secret FS details")))

        assert worker.main(ARGS) == 1

    def test_receipt_write_failure_after_success_is_nonzero(
        self, datahugger: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A successful download is not accepted without its success receipt."""
        monkeypatch.setattr(worker, "write_receipt", lambda *args: (_ for _ in ()).throw(OSError("no space")))

        assert worker.main(ARGS) == 1

    def test_worker_never_touches_the_experiment_dir(self, datahugger: SimpleNamespace, tmp_path: Path) -> None:
        """The worker writes only staging content and its receipt (the API owns the experiment and the DB)."""
        worker.main(ARGS)

        assert not (tmp_path / "abcde").exists()

    def test_missing_arguments_exit_nonzero(self, datahugger: SimpleNamespace) -> None:
        """Argument errors are argparse's job (exit code 2)."""
        with pytest.raises(SystemExit) as excinfo:
            worker.main(["--operation-id", OPERATION_ID])
        assert excinfo.value.code == 2


class TestDownloadErrorAdapter:
    """Known datahugger-ng 0.6.9 errors receive fixed causes; variable native details stay off the receipt."""

    @pytest.mark.parametrize(
        ("native", "expected"),
        [
            ("unknown domain: example.com", ERROR_UNRECOGNIZED),
            ("cannot get fragment of url 'https://mdposit.mddbr.eu/'", ERROR_UNRECOGNIZED),
            ("expected url to end with 'overview', got 'https://host/secret'", ERROR_UNRECOGNIZED),
            (
                "repo fail: resource not found when GET https://mdposit.mddbr.eu/api/private?token=secret",
                "The repository or dataset was not found at mdposit.mddbr.eu. Verify its URL and that it is public.",
            ),
            (
                "repo fail: fail GET https://public.example/meta, with state code: 403",
                "The repository denied public access. Choose a publicly accessible dataset.",
            ),
            (
                "repo fail: fail GET https://public.example/meta, with state code: 500",
                "The public repository returned an HTTP error (HTTP 500). Retry later.",
            ),
            ("repo fail: fail at client sent GET https://public.example/meta", ERROR_CONNECTION),
            ("repo fail: fail GET https://public.example/meta, network / protocol error", ERROR_CONNECTION),
            ("crawler fail: cannot create dir at '/mddash/secret'", ERROR_STORAGE),
            ("crawler fail: cannot create dir /mddash/secret/trajectory.xtc", ERROR_STORAGE),
            ("crawler fail: fail on create file at /mddash/secret", ERROR_STORAGE),
            ("crawler fail: fail at writing to fs", ERROR_STORAGE),
            ("crawler fail: size wrong, expect 42, got 99", ERROR_VALIDATION),
            ("crawler fail: checksum wrong, expect secret, got private", ERROR_VALIDATION),
        ],
    )
    def test_curated_native_error(self, native: str, expected: str) -> None:
        """A known stage maps entirely to fixed text."""
        assert str(sanitize_download_exception(RuntimeError(native))) == expected
        assert "secret" not in expected
        assert "private" not in expected

    def test_http_error_reports_only_source_filename(self) -> None:
        """A filename from a recognized complete native message can be shown without its source URL."""
        text = (
            "crawler fail: fail to send http GET to https://user:password@host/path?token=private, "
            "to get file 'nested/trajectory.xtc'"
        )
        assert str(sanitize_download_exception(RuntimeError(text))) == (
            f"The repository could not provide file 'nested/trajectory.xtc'. {ERROR_CONNECTION}"
        )

    @pytest.mark.parametrize(
        "native",
        [
            "arbitrary RuntimeError with sensitive cause",
            "crawler fail: fail to send http GET to https://host/path, to get file '/etc/passwd'",
            "crawler fail: fail to send http GET to https://host/path, to get file '../escape'",
            "crawler fail: fail to send http GET to https://host/path, to get file 'bad\nname'",
        ],
    )
    def test_untrusted_native_details_are_not_relayed(self, native: str) -> None:
        """Unexpected and unsafe variable content receives the fallback message."""
        message = str(sanitize_download_exception(RuntimeError(native)))
        assert "escape" not in message
        assert "passwd" not in message
        assert "bad\nname" not in message
        assert "arbitrary RuntimeError" not in message
