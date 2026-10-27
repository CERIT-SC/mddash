"""Tests for the per-user usage ledger and the report built from it."""

from datetime import UTC, datetime
from http import HTTPStatus
from typing import Any
from unittest.mock import MagicMock

import pytest
from enums import JobStatus, UsageOutcome
from flask.testing import FlaskClient
from models import MdrunJob, MdrunUsage
from pytest_mock import MockerFixture
from sqlalchemy.orm import Session
from usage import estimated_cost, main, summarize

POD_START = datetime(2026, 10, 1, 8, 0, tzinfo=UTC)
POD_END = datetime(2026, 10, 1, 10, 30, tzinfo=UTC)
OCT_1 = datetime(2026, 10, 1, tzinfo=UTC)
NOV_1 = datetime(2026, 11, 1, tzinfo=UTC)

GMX_GPU_JOB = {
    "experiment_id": "exp1",
    "tpr_name": "md.tpr",
    "bucket_name": "mddash-user-alice",
    "pme": "cpu",
    "nb": "gpu",
    "np": 2,
    "ntomp": 8,
    "owner": "alice@example.org",
    "owner_namespace": "mddash-user-alice-ns",
}
AMBER_JOB = {
    "experiment_id": "exp1",
    "prmtop_name": "sys.prmtop",
    "inpcrd_name": "sys.rst7",
    "mdin_name": "prod.in",
    "bucket_name": "mddash-user-alice",
    "ewald": "default",
    "owner": "alice@example.org",
    "owner_namespace": "mddash-user-alice-ns",
}


def _utc(value: datetime | None) -> datetime:
    """SQLite hands datetimes back naive; the ledger stores UTC."""
    assert value is not None
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value


@pytest.fixture
def pod_times(mocker: MockerFixture) -> MagicMock:
    return mocker.patch("k8s_client.get_pod_times", return_value=(POD_START, POD_END))


def _submit(client: FlaskClient, payload: dict[str, Any] = GMX_GPU_JOB, engine: str = "gmx") -> str:
    response = client.post(f"/api/jobs/{engine}", json=payload)
    assert response.status_code == HTTPStatus.CREATED, response.get_json()
    return response.get_json()["id"]


def _usage(db_session: Session, job_id: str) -> MdrunUsage:
    db_session.expire_all()
    record = db_session.get(MdrunUsage, job_id)
    assert record is not None
    return record


class TestAttribution:
    """Job creation records who asked for which resources."""

    def test_gmx_job_records_owner_and_requested_resources(
        self, client: FlaskClient, db_session: Session, mock_k8s_client: dict[str, Any]
    ) -> None:
        record = _usage(db_session, _submit(client))

        assert (record.owner, record.owner_namespace, record.engine) == (
            "alice@example.org",
            "mddash-user-alice-ns",
            "gmx",
        )
        assert (record.cpu_cores, record.memory_gib, record.gpus) == (16, 8, 1)
        assert (record.started_at, record.finished_at, record.outcome) == (None, None, None)

    @pytest.mark.parametrize(
        ("binary", "np", "ntomp", "expected"),
        [
            ("pmemd.cuda", 1, 4, (4, 4, 1)),
            ("pmemd.MPI", 4, 2, (8, 16, 0)),
        ],
    )
    def test_amber_job_records_requested_resources(
        self,
        client: FlaskClient,
        db_session: Session,
        mock_k8s_client: dict[str, Any],
        binary: str,
        np: int,
        ntomp: int,
        expected: tuple[int, int, int],
    ) -> None:
        job_id = _submit(client, {**AMBER_JOB, "binary": binary, "np": np, "ntomp": ntomp}, engine="amber")

        record = _usage(db_session, job_id)

        assert record.engine == "amber"
        assert (record.cpu_cores, record.memory_gib, record.gpus) == expected

    def test_owner_reaches_the_kubernetes_job(self, client: FlaskClient, mock_k8s_client: dict[str, Any]) -> None:
        _submit(client)

        kwargs = mock_k8s_client["create_gromacs_job"].call_args.kwargs
        assert (kwargs["owner"], kwargs["owner_namespace"]) == ("alice@example.org", "mddash-user-alice-ns")

    def test_request_without_owner_is_recorded_unattributed(
        self, client: FlaskClient, db_session: Session, mock_k8s_client: dict[str, Any]
    ) -> None:
        legacy_payload = {k: v for k, v in GMX_GPU_JOB.items() if k not in {"owner", "owner_namespace"}}

        record = _usage(db_session, _submit(client, legacy_payload))

        assert (record.owner, record.owner_namespace) == (None, None)

    def test_invalid_owner_namespace_is_rejected_before_the_job_starts(
        self, client: FlaskClient, db_session: Session, mock_k8s_client: dict[str, Any]
    ) -> None:
        response = client.post("/api/jobs/gmx", json={**GMX_GPU_JOB, "owner_namespace": "Alice_NS"})

        assert response.status_code == HTTPStatus.BAD_REQUEST
        assert response.content_type == "application/problem+json"
        mock_k8s_client["create_gromacs_job"].assert_not_called()
        assert db_session.query(MdrunUsage).count() == 0


class TestAllocationWindow:
    """The window runs from the pod's start to its last container exit, with request-time fallbacks."""

    def test_running_transition_stamps_the_pod_start(
        self, client: FlaskClient, db_session: Session, mock_k8s_client: dict[str, Any], pod_times: MagicMock
    ) -> None:
        job_id = _submit(client)
        mock_k8s_client["get_job_status"].return_value = JobStatus.RUNNING
        pod_times.return_value = (POD_START, None)

        client.get(f"/api/jobs/gmx/{job_id}")

        record = _usage(db_session, job_id)
        assert _utc(record.started_at) == POD_START
        assert record.finished_at is None

    @pytest.mark.parametrize(
        ("status", "outcome"),
        [(JobStatus.FINISHED, UsageOutcome.FINISHED), (JobStatus.ERROR, UsageOutcome.ERROR)],
    )
    def test_terminal_transition_reads_the_pod_before_deleting_the_job(
        self,
        client: FlaskClient,
        db_session: Session,
        mock_k8s_client: dict[str, Any],
        pod_times: MagicMock,
        mocker: MockerFixture,
        status: JobStatus,
        outcome: UsageOutcome,
    ) -> None:
        job_id = _submit(client)
        mock_k8s_client["get_job_status"].return_value = status
        calls = mocker.MagicMock()
        calls.attach_mock(pod_times, "get_pod_times")
        calls.attach_mock(mock_k8s_client["delete_job"], "delete_job")

        client.get(f"/api/jobs/gmx/{job_id}")

        record = _usage(db_session, job_id)
        assert (_utc(record.started_at), _utc(record.finished_at), record.outcome) == (POD_START, POD_END, outcome)
        # Deleting the Job removes its pod, and with it the timestamps.
        assert [name for name, *_ in calls.mock_calls] == ["get_pod_times", "delete_job"]

    def test_missing_pod_times_fall_back_to_observation_time(
        self, client: FlaskClient, db_session: Session, mock_k8s_client: dict[str, Any], pod_times: MagicMock
    ) -> None:
        job_id = _submit(client)
        mock_k8s_client["get_job_status"].return_value = JobStatus.FINISHED
        pod_times.return_value = (None, None)

        before = datetime.now(UTC)
        client.get(f"/api/jobs/gmx/{job_id}")
        after = datetime.now(UTC)

        record = _usage(db_session, job_id)
        assert before <= _utc(record.started_at) <= _utc(record.finished_at) <= after

    def test_stop_closes_the_window_at_request_time(
        self, client: FlaskClient, db_session: Session, mock_k8s_client: dict[str, Any], pod_times: MagicMock
    ) -> None:
        job_id = _submit(client)
        mock_k8s_client["get_job_status"].return_value = JobStatus.RUNNING
        pod_times.return_value = (POD_START, None)
        client.get(f"/api/jobs/gmx/{job_id}")

        before = datetime.now(UTC)
        response = client.post(f"/api/jobs/gmx/{job_id}/stop")
        after = datetime.now(UTC)

        assert response.status_code == HTTPStatus.NO_CONTENT
        record = _usage(db_session, job_id)
        assert _utc(record.started_at) == POD_START
        assert before <= _utc(record.finished_at) <= after
        assert record.outcome == UsageOutcome.STOPPED

    def test_delete_closes_a_live_window_and_keeps_the_ledger_row(
        self, client: FlaskClient, db_session: Session, mock_k8s_client: dict[str, Any], pod_times: MagicMock
    ) -> None:
        job_id = _submit(client)
        mock_k8s_client["get_job_status"].return_value = JobStatus.RUNNING
        pod_times.return_value = (POD_START, None)
        client.get(f"/api/jobs/gmx/{job_id}")

        before = datetime.now(UTC)
        response = client.delete(f"/api/jobs/gmx/{job_id}")
        after = datetime.now(UTC)

        assert response.status_code == HTTPStatus.NO_CONTENT
        record = _usage(db_session, job_id)
        assert db_session.get(MdrunJob, job_id) is None
        assert before <= _utc(record.finished_at) <= after
        assert record.outcome == UsageOutcome.DELETED

    def test_delete_after_finish_keeps_the_finished_window(
        self, client: FlaskClient, db_session: Session, mock_k8s_client: dict[str, Any], pod_times: MagicMock
    ) -> None:
        job_id = _submit(client)
        mock_k8s_client["get_job_status"].return_value = JobStatus.FINISHED
        client.get(f"/api/jobs/gmx/{job_id}")

        client.delete(f"/api/jobs/gmx/{job_id}")

        record = _usage(db_session, job_id)
        assert (_utc(record.finished_at), record.outcome) == (POD_END, UsageOutcome.FINISHED)

    def test_vanished_job_closes_once_and_keeps_its_status(
        self, client: FlaskClient, db_session: Session, mock_k8s_client: dict[str, Any], pod_times: MagicMock
    ) -> None:
        job_id = _submit(client)
        mock_k8s_client["get_job_status"].return_value = JobStatus.RUNNING
        pod_times.return_value = (POD_START, None)
        client.get(f"/api/jobs/gmx/{job_id}")
        mock_k8s_client["get_job_status"].return_value = JobStatus.UNKNOWN
        pod_times.return_value = (None, None)

        response = client.get(f"/api/jobs/gmx/{job_id}")
        closed_at = _utc(_usage(db_session, job_id).finished_at)
        client.get(f"/api/jobs/gmx/{job_id}")

        assert response.get_json()["status"] == "running"
        record = _usage(db_session, job_id)
        assert (_utc(record.started_at), record.outcome) == (POD_START, UsageOutcome.UNKNOWN)
        assert _utc(record.finished_at) == closed_at

    def test_job_created_before_the_ledger_still_transitions(
        self, client: FlaskClient, db_session: Session, mock_k8s_client: dict[str, Any], pod_times: MagicMock
    ) -> None:
        db_session.add(MdrunJob(id="legacy", job_name="mdrun-legacy", experiment_id="exp1"))
        db_session.commit()
        mock_k8s_client["get_job_status"].return_value = JobStatus.FINISHED

        response = client.get("/api/jobs/gmx/legacy")

        assert response.get_json()["status"] == "finished"
        mock_k8s_client["delete_job"].assert_called_once()
        assert db_session.query(MdrunUsage).count() == 0


def _record(
    owner: str | None,
    start: datetime | None,
    end: datetime | None,
    *,
    cpu: int = 4,
    memory: int = 8,
    gpus: int = 0,
) -> MdrunUsage:
    return MdrunUsage(
        job_id=f"{owner}-{start}",
        engine="gmx",
        owner=owner,
        owner_namespace=f"ns-{owner}" if owner else None,
        experiment_id="exp1",
        cpu_cores=cpu,
        memory_gib=memory,
        gpus=gpus,
        started_at=start,
        finished_at=end,
    )


class TestSummarize:
    """Per-owner totals over a period."""

    def test_windows_are_clipped_to_the_period(self) -> None:
        # Four hours of allocation, two of them in October.
        record = _record(
            "alice",
            datetime(2026, 9, 30, 22, tzinfo=UTC),
            datetime(2026, 10, 1, 2, tzinfo=UTC),
            cpu=16,
            memory=32,
            gpus=1,
        )

        [row] = summarize([record], since=OCT_1, until=NOV_1, now=NOV_1)

        assert (row.jobs, row.cpu_core_hours, row.gpu_hours, row.memory_gib_hours) == (1, 32.0, 2.0, 64.0)

    def test_open_windows_run_until_now(self) -> None:
        record = _record("alice", datetime(2026, 10, 10, tzinfo=UTC), None, gpus=1)

        [row] = summarize([record], since=OCT_1, until=NOV_1, now=datetime(2026, 10, 10, 3, tzinfo=UTC))

        assert row.gpu_hours == pytest.approx(3.0)

    def test_naive_timestamps_from_sqlite_are_utc(self) -> None:
        record = _record("alice", datetime(2026, 10, 1, 8), datetime(2026, 10, 1, 9), gpus=1)

        [row] = summarize([record], since=OCT_1, until=NOV_1, now=NOV_1)

        assert row.gpu_hours == pytest.approx(1.0)

    def test_jobs_outside_the_period_or_never_started_count_nothing(self) -> None:
        records = [
            _record("alice", datetime(2026, 9, 1, tzinfo=UTC), datetime(2026, 9, 2, tzinfo=UTC)),
            _record("bob", None, None),
            _record("carol", None, datetime(2026, 10, 5, tzinfo=UTC)),
        ]

        assert summarize(records, since=OCT_1, until=NOV_1, now=NOV_1) == []

    def test_usage_is_grouped_per_owner_with_unattributed_kept_apart(self) -> None:
        day = datetime(2026, 10, 2, tzinfo=UTC)
        hour = datetime(2026, 10, 2, 1, tzinfo=UTC)
        records = [
            _record("alice", day, hour, gpus=1),
            _record("alice", hour, datetime(2026, 10, 2, 2, tzinfo=UTC), gpus=1),
            _record("bob", day, hour, cpu=32),
            _record(None, day, hour, cpu=8),
        ]

        rows = summarize(records, since=OCT_1, until=NOV_1, now=NOV_1)

        assert [(r.owner, r.owner_namespace, r.jobs, r.gpu_hours, r.cpu_core_hours) for r in rows] == [
            ("alice", "ns-alice", 2, 2.0, 8.0),
            ("bob", "ns-bob", 1, 0.0, 32.0),
            (None, None, 1, 0.0, 8.0),
        ]


class TestEstimatedCost:
    """Cost uses the Tuner's hourly rates when configured."""

    def test_cost_sums_cpu_gpu_and_memory_rates(self, mocker: MockerFixture) -> None:
        mocker.patch.multiple("usage", COST_CPU_CORE_HOUR=0.04, COST_GPU_HOUR=1.20, COST_GB_RAM_HOUR=0.005)
        record = _record("alice", OCT_1, datetime(2026, 10, 1, 2, tzinfo=UTC), cpu=16, memory=32, gpus=1)
        [row] = summarize([record], since=OCT_1, until=NOV_1, now=NOV_1)

        # 32 core-h * 0.04 + 2 GPU-h * 1.20 + 64 GiB-h * 0.005
        assert estimated_cost(row) == pytest.approx(4.0)

    def test_cost_is_unknown_without_rates(self, mocker: MockerFixture) -> None:
        mocker.patch.multiple("usage", COST_CPU_CORE_HOUR=None, COST_GPU_HOUR=1.20, COST_GB_RAM_HOUR=0.005)
        record = _record("alice", OCT_1, datetime(2026, 10, 1, 2, tzinfo=UTC), gpus=1)
        [row] = summarize([record], since=OCT_1, until=NOV_1, now=NOV_1)

        assert estimated_cost(row) is None


class TestReportCli:
    """`python -m usage` prints the ledger summary for operators."""

    def test_csv_has_one_row_per_owner(
        self, db_session: Session, mocker: MockerFixture, capsys: pytest.CaptureFixture[str]
    ) -> None:
        mocker.patch.multiple("usage", COST_CPU_CORE_HOUR=None, COST_GPU_HOUR=None, COST_GB_RAM_HOUR=None)
        db_session.add_all([
            _record("alice", datetime(2026, 10, 3, tzinfo=UTC), datetime(2026, 10, 3, 2, tzinfo=UTC), gpus=1),
            _record(None, datetime(2026, 10, 3, tzinfo=UTC), datetime(2026, 10, 3, 1, tzinfo=UTC)),
        ])
        db_session.commit()

        main(["--since", "2026-10-01", "--until", "2026-11-01", "--csv"])

        assert capsys.readouterr().out.splitlines() == [
            "user,namespace,jobs,cpu_core_hours,gpu_hours,memory_gib_hours,estimated_cost",
            "alice,ns-alice,1,8.00,2.00,16.00,",
            ",,1,4.00,0.00,8.00,",
        ]
