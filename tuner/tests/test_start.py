import pytest
from api import start


def test_startup_rejects_missing_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("TUNER_USER", raising=False)
    monkeypatch.delenv("TUNER_PASSWORD", raising=False)

    with pytest.raises(RuntimeError, match="TUNER_USER, TUNER_PASSWORD"):
        start.validate_config()


@pytest.mark.parametrize("var", ["COST_CPU_CORE_HOUR", "COST_GPU_HOUR", "COST_GB_RAM_HOUR"])
def test_startup_rejects_missing_pricing(monkeypatch: pytest.MonkeyPatch, var: str) -> None:
    monkeypatch.delenv(var, raising=False)

    with pytest.raises(RuntimeError, match=var):
        start.validate_config()
