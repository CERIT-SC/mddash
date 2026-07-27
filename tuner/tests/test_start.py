import pytest
from api import start


def test_startup_rejects_missing_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(start, "TUNER_USER", "")
    monkeypatch.setattr(start, "TUNER_PASSWORD", "")

    with pytest.raises(RuntimeError, match="TUNER_USER and TUNER_PASSWORD"):
        start.validate_config()
