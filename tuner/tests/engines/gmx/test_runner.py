import signal
from unittest.mock import MagicMock

import pytest
from api.engines.gmx import runner


def test_monitor_interruption_terminates_native_process_group(tmp_path, monkeypatch) -> None:
    process = MagicMock()
    process.poll.return_value = None
    monkeypatch.setattr(runner.subprocess, "Popen", MagicMock(return_value=process))
    monkeypatch.setattr(runner, "_monitor_process", MagicMock(side_effect=KeyboardInterrupt))
    terminate = MagicMock()
    monkeypatch.setattr(runner, "_terminate_process_group", terminate)

    with pytest.raises(KeyboardInterrupt):
        runner._run_command_with_monitoring(
            ["gmx"],
            tmp_path / "stdout.log",
            tmp_path / "stderr.log",
            {},
            tmp_path,
            "test trial",
            0.0,
        )

    terminate.assert_called_once_with(process, signal.SIGTERM)
    process.wait.assert_called_once_with(timeout=30)
