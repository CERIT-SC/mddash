from types import SimpleNamespace

from api.db import operations
from api.schemas.common import JobStatus
from sqlalchemy.orm.exc import StaleDataError


class _Result:
    def scalar_one_or_none(self) -> SimpleNamespace:
        return SimpleNamespace(status=JobStatus.PENDING, performance=None)


class _StaleSession:
    def __enter__(self) -> "_StaleSession":
        return self

    def __exit__(self, exc_type: object, exc_value: object, traceback: object) -> None:
        return None

    def execute(self, statement: object) -> _Result:
        return _Result()

    def commit(self) -> None:
        raise StaleDataError("trial was deleted concurrently")

    def rollback(self) -> None:
        pass


def test_update_trial_result_returns_false_when_trial_is_deleted_during_commit(monkeypatch) -> None:
    monkeypatch.setattr(operations, "get_session", _StaleSession)

    updated = operations.update_trial_result(217, JobStatus.ERROR, None)

    assert updated is False
