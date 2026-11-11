"""Tests for the Prometheus metrics derived from the usage ledger."""

from datetime import UTC, datetime, timedelta

import pytest
from enums import UsageOutcome
from flask import Flask
from metrics import LedgerCollector
from models import MdrunUsage, MdrunUsageMeasurement
from prometheus_client import CollectorRegistry
from sqlalchemy.orm import Session

NOW = datetime(2026, 11, 4, 12, 0, tzinfo=UTC)
ALICE_GMX = {"user": "alice@example.org", "namespace": "mddash-user-alice-ns", "engine": "gmx"}
ALICE_AMBER = {**ALICE_GMX, "engine": "amber"}
UNMEASURED = {
    "mddash_mdrun_measured_jobs": 0,
    "mddash_mdrun_measured_cpu_core_seconds_used": 0,
    "mddash_mdrun_measured_cpu_core_seconds_allocated": 0,
    "mddash_mdrun_measured_gpu_seconds_busy": 0,
    "mddash_mdrun_measured_gpu_seconds_allocated": 0,
    "mddash_mdrun_measured_container_seconds": 0,
    "mddash_mdrun_measured_cpu_stall_seconds": 0,
    "mddash_mdrun_measured_oom_kills": 0,
    "mddash_mdrun_measured_gpu_energy_joules": 0,
}
NOTHING_PENDING = {"mddash_mdrun_pending_jobs": 0, "mddash_mdrun_pending_gpus": 0}


def _row(
    job_id: str,
    *,
    engine: str = "gmx",
    owner: str | None = "alice@example.org",
    owner_namespace: str | None = "mddash-user-alice-ns",
    cpu_cores: int = 4,
    memory_gib: int = 4,
    gpus: int = 0,
    created_at: datetime | None = None,
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
        created_at=created_at or started_at or NOW,
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
            _row("legacy-client", owner=None, owner_namespace=None, started_at=NOW - timedelta(hours=1)),
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
            "mddash_mdrun_queue_wait_seconds": 0,
            "mddash_mdrun_cpu_core_seconds": 158_400,  # 16 cores x 2.5 h + 4 cores x 1 h so far
            "mddash_mdrun_gpu_seconds": 9_000,
            "mddash_mdrun_memory_gib_seconds": 86_400,  # 8 GiB x 2.5 h + 4 GiB x 1 h so far
            "mddash_mdrun_allocated_cpu_cores": 4,
            "mddash_mdrun_allocated_gpus": 0,
            "mddash_mdrun_allocated_memory_gib": 4,
            **NOTHING_PENDING,
            **UNMEASURED,
        }
        assert _samples(registry, ALICE_AMBER) == {
            "mddash_mdrun_jobs_started": 1,
            "mddash_mdrun_queue_wait_seconds": 0,
            "mddash_mdrun_cpu_core_seconds": 3_600,
            "mddash_mdrun_gpu_seconds": 3_600,
            "mddash_mdrun_memory_gib_seconds": 14_400,
            "mddash_mdrun_allocated_cpu_cores": 0,
            "mddash_mdrun_allocated_gpus": 0,
            "mddash_mdrun_allocated_memory_gib": 0,
            **NOTHING_PENDING,
            **UNMEASURED,
        }
        unattributed = _samples(registry, {"user": "", "namespace": "", "engine": "gmx"})
        assert unattributed["mddash_mdrun_cpu_core_seconds"] == 14_400  # 4 cores x 1 h

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
            "mddash_mdrun_measured_container_seconds": 0,
            "mddash_mdrun_measured_cpu_stall_seconds": 0,
            "mddash_mdrun_measured_oom_kills": 0,
            "mddash_mdrun_measured_gpu_energy_joules": 0,
        }

    def test_measured_jobs_report_their_diagnostics(self, registry: CollectorRegistry, db_session: Session) -> None:
        container_start = NOW - timedelta(hours=3, minutes=55)
        db_session.add(
            _row(
                "diagnosed",
                gpus=1,
                started_at=NOW - timedelta(hours=4),
                finished_at=NOW - timedelta(hours=1),
                outcome=UsageOutcome.FINISHED,
                # The container ran 2 h with tasks waiting for CPU for 30 min, on one GPU half busy drawing 200 W.
                measurement=MdrunUsageMeasurement(
                    job_id="diagnosed",
                    cpu_core_seconds=3_600.0,
                    gpu_utilization=50.0,
                    complete=True,
                    container_started_at=container_start,
                    measured_at=container_start + timedelta(hours=2),
                    cpu_stall_seconds=1_800.0,
                    oom_kills=1,
                    gpu_power_watts=200.0,
                ),
            )
        )
        db_session.commit()

        samples = _samples(registry, ALICE_GMX)

        assert (
            samples["mddash_mdrun_measured_container_seconds"],
            samples["mddash_mdrun_measured_cpu_stall_seconds"],
            samples["mddash_mdrun_measured_oom_kills"],
            samples["mddash_mdrun_measured_gpu_energy_joules"],
        ) == (7_200, 1_800, 1, 1_440_000)
        # The GPU idled outside the container's 2 h: 1 h busy of the 3 h window.
        assert (
            samples["mddash_mdrun_measured_gpu_seconds_busy"],
            samples["mddash_mdrun_measured_gpu_seconds_allocated"],
        ) == (3_600, 10_800)

    def test_waiting_jobs_and_queue_wait(self, registry: CollectorRegistry, db_session: Session) -> None:
        db_session.add_all([
            _row("queued", gpus=2, created_at=NOW - timedelta(minutes=10)),
            _row(
                "waited",
                created_at=NOW - timedelta(hours=2),
                started_at=NOW - timedelta(hours=1, minutes=30),
                finished_at=NOW - timedelta(hours=1),
                outcome=UsageOutcome.FINISHED,
            ),
        ])
        db_session.commit()

        samples = _samples(registry, ALICE_GMX)

        assert (samples["mddash_mdrun_pending_jobs"], samples["mddash_mdrun_pending_gpus"]) == (1, 2)
        assert (samples["mddash_mdrun_jobs_started"], samples["mddash_mdrun_queue_wait_seconds"]) == (1, 1_800)

    def test_cumulative_usage_is_exported_as_gauges(self, registry: CollectorRegistry) -> None:
        """A late-noticed exit steps a total back, which Prometheus would read as a counter reset."""
        assert {family.type for family in registry.collect()} == {"gauge"}
