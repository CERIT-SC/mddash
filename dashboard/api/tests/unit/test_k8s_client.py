"""Tests for lazy dashboard Kubernetes client initialization."""

import importlib
from pathlib import Path

from pytest_mock import MockerFixture


def test_importing_k8s_client_does_not_load_incluster_config(
    tmp_path: Path,
    monkeypatch,  # noqa: ANN001
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

    from clients import k8s  # noqa: PLC0415

    importlib.reload(k8s)

    load_config.assert_not_called()
    core_api.assert_not_called()
    batch_api.assert_not_called()

    k8s.reset_k8s_clients_for_tests()


def test_get_core_v1_loads_config_once(mocker: MockerFixture) -> None:
    """First Kubernetes use should initialize config once and cache clients."""
    from clients import k8s  # noqa: PLC0415

    k8s.reset_k8s_clients_for_tests()
    load_config = mocker.patch("clients.k8s.config.load_incluster_config")
    core_api = mocker.patch("clients.k8s.CoreV1Api")

    first = k8s.get_core_v1()
    second = k8s.get_core_v1()

    assert first is second
    load_config.assert_called_once_with()
    core_api.assert_called_once_with()


def test_get_batch_v1_loads_config_once(mocker: MockerFixture) -> None:
    """Batch client creation should share the same in-cluster config load."""
    from clients import k8s  # noqa: PLC0415

    k8s.reset_k8s_clients_for_tests()
    load_config = mocker.patch("clients.k8s.config.load_incluster_config")
    batch_api = mocker.patch("clients.k8s.BatchV1Api")

    first = k8s.get_batch_v1()
    second = k8s.get_batch_v1()

    assert first is second
    load_config.assert_called_once_with()
    batch_api.assert_called_once_with()
