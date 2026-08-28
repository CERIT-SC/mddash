"""Tests for lazy dashboard Kubernetes client initialization and pod info mapping."""

import importlib
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock

from enums import PodStatus
from pytest_mock import MockerFixture


def test_importing_k8s_client_does_not_load_incluster_config(
    tmp_path: Path,
    monkeypatch,
    mocker: MockerFixture,
) -> None:
    """Importing the client module should not touch Kubernetes configuration."""
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("POD_NAMESPACE", "test-namespace")
    monkeypatch.setenv("PVC_NAME", "test-pvc")
    monkeypatch.setenv("PVC_STORAGE_SIZE", "1Gi")
    monkeypatch.setenv("TUNER_USER", "tuner")
    monkeypatch.setenv("TUNER_PASSWORD", "secret")

    load_config = mocker.patch("kubernetes.config.load_incluster_config")
    core_api = mocker.patch("kubernetes.client.CoreV1Api")
    batch_api = mocker.patch("kubernetes.client.BatchV1Api")

    from clients import k8s

    importlib.reload(k8s)

    load_config.assert_not_called()
    core_api.assert_not_called()
    batch_api.assert_not_called()

    k8s.reset_k8s_clients_for_tests()


def test_get_core_v1_loads_config_once(mocker: MockerFixture) -> None:
    """First Kubernetes use should initialize config once and cache clients."""
    from clients import k8s

    k8s.reset_k8s_clients_for_tests()
    load_config = mocker.patch("kubernetes.config.load_incluster_config")
    core_api = mocker.patch("kubernetes.client.CoreV1Api")

    first = k8s.get_core_v1()
    second = k8s.get_core_v1()

    assert first is second
    load_config.assert_called_once_with()
    core_api.assert_called_once_with()


def test_get_batch_v1_loads_config_once(mocker: MockerFixture) -> None:
    """Batch client creation should share the same in-cluster config load."""
    from clients import k8s

    k8s.reset_k8s_clients_for_tests()
    load_config = mocker.patch("kubernetes.config.load_incluster_config")
    batch_api = mocker.patch("kubernetes.client.BatchV1Api")

    first = k8s.get_batch_v1()
    second = k8s.get_batch_v1()

    assert first is second
    load_config.assert_called_once_with()
    batch_api.assert_called_once_with()


class TestGetPodInfo:
    """get_pod_info maps one pod read to a (status, start_time) tuple."""

    def _mock_pod(self, phase: str, started: datetime | None) -> MagicMock:
        pod = MagicMock()
        pod.metadata.deletion_timestamp = None
        pod.status.phase = phase
        pod.status.container_statuses = []
        pod.status.start_time = started
        return pod

    def test_running_pod_reports_start_time(self, mocker: MockerFixture) -> None:
        from clients import k8s

        started = datetime(2026, 8, 17, 12, 0, tzinfo=timezone.utc)
        core = MagicMock()
        core.read_namespaced_pod.return_value = self._mock_pod("Running", started)
        mocker.patch("clients.k8s.get_core_v1", return_value=core)

        assert k8s.get_pod_info("notebook-exp1") == (PodStatus.RUNNING, started)

    def test_pending_pod_may_lack_start_time(self, mocker: MockerFixture) -> None:
        from clients import k8s

        core = MagicMock()
        core.read_namespaced_pod.return_value = self._mock_pod("Pending", None)
        mocker.patch("clients.k8s.get_core_v1", return_value=core)

        assert k8s.get_pod_info("notebook-exp1") == (PodStatus.PENDING, None)

    def test_missing_pod_is_down_without_start_time(self, mocker: MockerFixture) -> None:
        from clients import k8s
        from kubernetes.client.rest import ApiException

        k8s._load_k8s()  # populate the module-global ApiException the except clause catches
        core = MagicMock()
        core.read_namespaced_pod.side_effect = ApiException(status=404)
        mocker.patch("clients.k8s.get_core_v1", return_value=core)

        assert k8s.get_pod_info("notebook-exp1") == (PodStatus.DOWN, None)
