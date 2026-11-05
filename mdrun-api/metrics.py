"""
Prometheus metrics computed from the usage ledger at scrape time, served by the poller on ``METRICS_PORT``.

Cumulative usage is a gauge, not a counter: a window closes at the container's exit, which the poller can notice
after a scrape already counted the job as running, so the total can step back. Usage over a period is the gauge's
value at the end minus its value at the start, which matches ``python -m usage`` for the same period.
Measured usage counts when a job ends, against its whole window, as in the report's efficiency. Queue wait counts
when a job starts, so its average over a period is the wait difference over the ``jobs_started`` difference.
"""

import logging
from collections.abc import Callable, Iterator
from dataclasses import dataclass, fields
from datetime import UTC, datetime

from extensions import db
from flask import Flask
from models import MdrunUsage
from prometheus_client import CollectorRegistry, start_http_server
from prometheus_client.core import GaugeMetricFamily
from prometheus_client.registry import Collector
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from usage import EPOCH, allocated_seconds, measured_seconds, queue_wait_seconds

logger = logging.getLogger(__name__)

LABELS = ("user", "namespace", "engine")


@dataclass
class _Usage:
    """One label set's totals; field names become metric names."""

    jobs_started: int = 0
    queue_wait_seconds: float = 0.0
    cpu_core_seconds: float = 0.0
    gpu_seconds: float = 0.0
    memory_gib_seconds: float = 0.0
    allocated_cpu_cores: int = 0
    allocated_gpus: int = 0
    allocated_memory_gib: int = 0
    pending_jobs: int = 0
    pending_gpus: int = 0
    measured_jobs: int = 0
    measured_cpu_core_seconds_used: float = 0.0
    measured_cpu_core_seconds_allocated: float = 0.0
    measured_gpu_seconds_busy: float = 0.0
    measured_gpu_seconds_allocated: float = 0.0
    measured_container_seconds: float = 0.0
    measured_cpu_stall_seconds: float = 0.0
    measured_oom_kills: int = 0
    measured_gpu_energy_joules: float = 0.0


_CUMULATIVE = "running jobs count up to now; take differences over time, never rate() or increase()"
_MEASURED = "jobs that measured themselves, counted when they end; take differences over time"
_HELP = {
    "jobs_started": "MDRun jobs that have held resources.",
    "queue_wait_seconds": "Seconds MDRun jobs waited from submission to pod start, counted when they start; "
    "divide its difference over time by jobs_started's.",
    "cpu_core_seconds": f"Allocated MDRun CPU core-seconds; {_CUMULATIVE}.",
    "gpu_seconds": f"Allocated MDRun GPU-seconds; {_CUMULATIVE}.",
    "memory_gib_seconds": f"Allocated MDRun memory GiB-seconds; {_CUMULATIVE}.",
    "allocated_cpu_cores": "CPU cores held by running MDRun jobs.",
    "allocated_gpus": "GPUs held by running MDRun jobs.",
    "allocated_memory_gib": "Memory GiB held by running MDRun jobs.",
    "pending_jobs": "MDRun jobs waiting for their pod to start.",
    "pending_gpus": "GPUs requested by MDRun jobs waiting for their pod to start.",
    "measured_jobs": f"MDRun {_MEASURED}.",
    "measured_cpu_core_seconds_used": f"CPU core-seconds used by MDRun {_MEASURED}.",
    "measured_cpu_core_seconds_allocated": f"CPU core-seconds allocated to MDRun {_MEASURED}.",
    "measured_gpu_seconds_busy": f"GPU-seconds the GPUs of MDRun {_MEASURED} were busy.",
    "measured_gpu_seconds_allocated": f"GPU-seconds allocated to MDRun {_MEASURED}.",
    "measured_container_seconds": f"Seconds the simulation containers of MDRun {_MEASURED} ran, counting those that "
    "reported CPU stall time.",
    "measured_cpu_stall_seconds": f"Seconds tasks of MDRun {_MEASURED} waited for CPU (pressure stall, some).",
    "measured_oom_kills": f"Processes the OOM killer ended in MDRun {_MEASURED}.",
    "measured_gpu_energy_joules": f"GPU energy of MDRun {_MEASURED}, from sampled power draw.",
}


class LedgerCollector(Collector):
    """Totals per user, namespace, and engine; unattributed jobs have empty user and namespace labels."""

    def __init__(self, app: Flask, now: Callable[[], datetime] = lambda: datetime.now(UTC)) -> None:
        """Read the ledger through ``app``'s database; ``now`` ends the open windows."""
        self._app = app
        self._now = now

    def collect(self) -> Iterator[GaugeMetricFamily]:
        """
        Read the whole ledger; it is small, and recomputing keeps the totals right across restarts.

        Yields:
            One gauge family per ``_Usage`` field.
        """
        now = self._now()
        totals: dict[tuple[str, str, str], _Usage] = {}
        with self._app.app_context():
            for record in db.session.scalars(select(MdrunUsage).options(selectinload(MdrunUsage.measurement))):
                usage = totals.setdefault((record.owner or "", record.owner_namespace or "", record.engine), _Usage())
                _add_record(usage, record, now)

        for field in fields(_Usage):
            family = GaugeMetricFamily(f"mddash_mdrun_{field.name}", _HELP[field.name], labels=LABELS)
            for labels, usage in totals.items():
                family.add_metric(labels, getattr(usage, field.name))
            yield family


def _add_record(usage: _Usage, record: MdrunUsage, now: datetime) -> None:
    if seconds := allocated_seconds(record, since=EPOCH, until=now, now=now):
        usage.jobs_started += 1
        usage.queue_wait_seconds += queue_wait_seconds(record, now) or 0.0
        usage.cpu_core_seconds += record.cpu_cores * seconds
        usage.gpu_seconds += record.gpus * seconds
        usage.memory_gib_seconds += record.memory_gib * seconds
    if record.started_at is not None and record.finished_at is None:
        usage.allocated_cpu_cores += record.cpu_cores
        usage.allocated_gpus += record.gpus
        usage.allocated_memory_gib += record.memory_gib
    if record.started_at is None and record.finished_at is None:
        usage.pending_jobs += 1
        usage.pending_gpus += record.gpus
    if measured := measured_seconds(record, now):
        usage.measured_jobs += 1
        usage.measured_cpu_core_seconds_used += measured.cpu_core_seconds_used
        usage.measured_cpu_core_seconds_allocated += measured.cpu_core_seconds_allocated
        usage.measured_gpu_seconds_busy += measured.gpu_seconds_busy
        usage.measured_gpu_seconds_allocated += measured.gpu_seconds_allocated
        usage.measured_container_seconds += measured.stall_window_seconds
        usage.measured_cpu_stall_seconds += measured.cpu_stall_seconds
        usage.measured_oom_kills += measured.oom_kills or 0
        usage.measured_gpu_energy_joules += measured.gpu_energy_joules or 0.0


def serve(app: Flask, port: int) -> None:
    """Serve the ledger metrics from a daemon thread."""
    registry = CollectorRegistry()
    registry.register(LedgerCollector(app))
    start_http_server(port, registry=registry)
    logger.info("Serving ledger metrics on port %d", port)
