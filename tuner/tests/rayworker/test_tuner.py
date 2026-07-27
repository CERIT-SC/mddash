from unittest.mock import Mock

from api.rayworker import tuner


def test_ensure_ray_initialized_uses_single_client_connection(monkeypatch) -> None:
    ray_mock = Mock()
    ray_mock.is_initialized.return_value = False
    monkeypatch.setattr(tuner, "ray", ray_mock)

    tuner._ensure_ray_initialized()

    ray_mock.init.assert_called_once()
    _, kwargs = ray_mock.init.call_args
    assert "allow_multiple" not in kwargs
