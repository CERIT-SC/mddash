"""Tests for the Prometheus metrics derived from the usage ledger."""

from datetime import UTC, datetime, timedelta

import pytest
from enums import UsageOutcome
from flask import Flask
from metrics import LedgerCollector, serve
from models import MdrunUsage, MdrunUsageMeasurement
from prometheus_client import CollectorRegistry
from pytest_mock import MockerFixture
from sqlalchemy.orm import Session

NOW = datetime(2026, 11, 4, 12, 0, tzinfo=UTC)
ALICE_GMX = {"user": "alice@example.org", "namespace": "mddash-user-alice-ns", "engine": "gmx"}
ALICE_AMBER = {**ALICE_GMX, "engine": "amber"}
METRICS_PORT = 9100
UNMEASURED = {
    "mddash_mdrun_measured_jobs": 0,
    "mddash_mdrun_measured_cpu_core_seconds_used": 0,
    "mddash_mdrun_measured_cpu_core_seconds_allocated": 0,
    "mddash_mdrun_measured_gpu_seconds_busy": 0,
    "mddash_mdrun_measured_gpu_seconds_allocated": 0,
}


def _row(
    job_id: str,
    *,
    engine: str = "gmx",
    owner: str | None = "alice@example.org",
    owner_namespace: str | None = "mddash-user-alice-ns",
    cpu_cores: int = 4,
    memory_gib: int = 4,
    gpus: int = 0,
    started_at: datetime | None = None,
    finished_at: datetime | None = None,
    outcome: UsageOutcome | None = None,
    measurement: MdrunUsageMeasurement | None = None,
) -> MdrunUsage:
    return MdrunUsage(
        job_id=job_id,
        engine=engine,
        owner=owner,
        owner_namespace=owner_namespace,
        experiment_id="exp1",
        cpu_cores=cpu_cores,
        memory_gib=memory_gib,
        gpus=gpus,
        started_at=started_at,
        finished_at=finished_at,
        outcome=outcome,
        measurement=measurement,
    )


def _samples(registry: CollectorRegistry, labels: dict[str, str]) -> dict[str, float]:
    """Every sample for one label set, by metric name."""
    return {
        sample.name: sample.value
        for family in registry.collect()
        for sample in family.samples
        if sample.labels == labels
    }


@pytest.fixture
def registry(app: Flask) -> CollectorRegistry:
    registry = CollectorRegistry()
    registry.register(LedgerCollector(app, now=lambda: NOW))
    return registry


class TestLedgerCollector:
    """Scrapes report the ledger's allocation per user, namespace, and engine."""

    def test_usage_accumulates_per_user_and_engine(self, registry: CollectorRegistry, db_session: Session) -> None:
        db_session.add_all([
            _row(
                "gmx-done",
                cpu_cores=16,
                memory_gib=8,
                gpus=1,
                started_at=NOW - timedelta(hours=4),
                finished_at=NOW - timedelta(hours=1, minutes=30),
                outcome=UsageOutcome.FINISHED,
            ),
            _row("gmx-running", started_at=NOW - timedelta(hours=1)),
            _row(
                "amber-done",
                engine="amber",
                cpu_cores=1,
                gpus=1,
                started_at=NOW - timedelta(hours=3),
                finished_at=NOW - timedelta(hours=2),
                outcome=UsageOutcome.FINISHED,
            ),
        ])
        db_session.commit()

        assert _samples(registry, ALICE_GMX) == {
            "mddash_mdrun_jobs_started": 2,
            "mddash_mdrun_cpu_core_seconds": 158_400,  # 16 cores x 2.5 h + 4 cores x 1 h so far
            "mddash_mdrun_gpu_seconds": 9_000,
            "mddash_mdrun_memory_gib_seconds": 86_400,  # 8 GiB x 2.5 h + 4 GiB x 1 h so far
            "mddash_mdrun_allocated_cpu_cores": 4,
            "mddash_mdrun_allocated_gpus": 0,
            "mddash_mdrun_allocated_memory_gib": 4,
            **UNMEASURED,
        }
        assert _samples(registry, ALICE_AMBER) == {
            "mddash_mdrun_jobs_started": 1,
            "mddash_mdrun_cpu_core_seconds": 3_600,
            "mddash_mdrun_gpu_seconds": 3_600,
            "mddash_mdrun_memory_gib_seconds": 14_400,
            "mddash_mdrun_allocated_cpu_cores": 0,
            "mddash_mdrun_allocated_gpus": 0,
            "mddash_mdrun_allocated_memory_gib": 0,
            **UNMEASURED,
        }

    def test_measured_jobs_report_what_they_used(self, registry: CollectorRegistry, db_session: Session) -> None:
        measured = MdrunUsageMeasurement(
            job_id="measured",
            cpu_core_seconds=28_800.0,
            memory_peak_gib=3.0,
            gpu_utilization=75.0,
            gpu_memory_peak_gib=5.0,
            complete=True,
        )
        db_session.add_all([
            _row(
                "measured",
                cpu_cores=8,
                gpus=1,
                started_at=NOW - timedelta(hours=4),
                finished_at=NOW - timedelta(hours=2),
                outcome=UsageOutcome.FINISHED,
                measurement=measured,
            ),
            _row("unmeasured", started_at=NOW - timedelta(hours=3), finished_at=NOW - timedelta(hours=2)),
            _row("running", started_at=NOW - timedelta(hours=1)),
        ])
        db_session.commit()

        samples = _samples(registry, ALICE_GMX)

        assert {name: value for name, value in samples.items() if name.startswith("mddash_mdrun_measured_")} == {
            "mddash_mdrun_measured_jobs": 1,
            "mddash_mdrun_measured_cpu_core_seconds_used": 28_800,
            "mddash_mdrun_measured_cpu_core_seconds_allocated": 57_600,  # 8 cores x 2 h
            "mddash_mdrun_measured_gpu_seconds_busy": 5_400,  # 75 % of 2 h
            "mddash_mdrun_measured_gpu_seconds_allocated": 7_200,
        }

    def test_jobs_that_never_held_resources_count_nothing(
        self, registry: CollectorRegistry, db_session: Session
    ) -> None:
        stopped_in_queue = NOW - timedelta(hours=1)
        db_session.add_all([
            _row("queued", gpus=1),
            _row(
                "stopped-in-queue",
                gpus=1,
                started_at=stopped_in_queue,
                finished_at=stopped_in_queue,
                outcome=UsageOutcome.STOPPED,
            ),
        ])
        db_session.commit()

        assert set(_samples(registry, ALICE_GMX).values()) == {0}

    def test_unattributed_jobs_have_empty_owner_labels(self, registry: CollectorRegistry, db_session: Session) -> None:
        db_session.add(_row("legacy-client", owner=None, owner_namespace=None, started_at=NOW - timedelta(hours=1)))
        db_session.commit()

        unattributed = _samples(registry, {"user": "", "namespace": "", "engine": "gmx"})

        assert unattributed["mddash_mdrun_cpu_core_seconds"] == 14_400  # 4 cores x 1 h

    def test_cumulative_usage_is_exported_as_gauges(self, registry: CollectorRegistry) -> None:
        """
        A window closes at the container's exit, which the poller can notice after a scrape counted the job as running.

        The total then steps back, which Prometheus would read as a counter reset and count again.
        """
        assert {family.type for family in registry.collect()} == {"gauge"}


def test_serve_publishes_the_ledger_on_the_port(app: Flask, db_session: Session, mocker: MockerFixture) -> None:
    start_http_server = mocker.patch("metrics.start_http_server")
    db_session.add(_row("done", started_at=NOW - timedelta(hours=2), finished_at=NOW - timedelta(hours=1)))
    db_session.commit()

    serve(app, METRICS_PORT)

    (port,) = start_http_server.call_args.args
    registry = start_http_server.call_args.kwargs["registry"]
    assert port == METRICS_PORT
    assert registry.get_sample_value("mddash_mdrun_jobs_started", ALICE_GMX) == 1
