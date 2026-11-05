"""
Per-user MDRun usage from the ledger: ``python -m usage [--since DATE] [--until DATE] [--jobs] [--csv]``.

Usage is allocation: the CPU cores, memory, and GPUs a job requested, times how long its pod held them. Jobs whose
container measured itself also show how much of that allocation they used.
"""

import argparse
import csv
import sys
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime

from config import COST_CPU_CORE_HOUR, COST_GB_RAM_HOUR, COST_GPU_HOUR
from extensions import db
from models import MdrunUsage, MdrunUsageMeasurement
from sqlalchemy import select
from sqlalchemy.orm import selectinload

SECONDS_PER_HOUR = 3600
SECONDS_PER_MINUTE = 60
JOULES_PER_KWH = 3_600_000
EPOCH = datetime(1970, 1, 1, tzinfo=UTC)
# User and namespace columns are left-aligned; the numbers after them right-aligned.
NAME_COLUMNS = 2
SUMMED_FIELDS = (
    "jobs",
    "cpu_core_hours",
    "gpu_hours",
    "memory_gib_hours",
    "measured_cpu_core_hours",
    "used_cpu_core_hours",
    "measured_gpu_hours",
    "busy_gpu_hours",
    "waited_jobs",
    "queue_wait_seconds",
    "stall_window_seconds",
    "cpu_stall_seconds",
    "diagnosed_jobs",
    "oom_kills",
    "gpu_energy_jobs",
    "gpu_energy_joules",
)
JOB_CSV_COLUMNS = (
    "job_id",
    "user",
    "namespace",
    "engine",
    "outcome",
    "started_at",
    "hours",
    "cpu_cores",
    "cpu_used_percent",
    "memory_gib",
    "memory_peak_gib",
    "gpus",
    "gpu_busy_percent",
    "gpu_memory_peak_gib",
    "measured_to_exit",
    "queue_wait_minutes",
    "startup_minutes",
    "ns_per_day",
    "cpu_throttled_percent",
    "cpu_stall_percent",
    "memory_stall_percent",
    "io_stall_percent",
    "oom_kills",
    "io_read_gib",
    "io_write_gib",
    "gpu_power_watts",
)
JOB_TABLE_COLUMNS = {
    "job_id": "Job",
    "user": "User",
    "engine": "Engine",
    "started_at": "Started",
    "hours": "Hours",
    "cpu_cores": "Cores",
    "cpu_used_percent": "CPU used %",
    "memory_gib": "Mem GiB",
    "memory_peak_gib": "Peak GiB",
    "gpus": "GPUs",
    "gpu_busy_percent": "GPU busy %",
    "gpu_memory_peak_gib": "GPU peak GiB",
    "queue_wait_minutes": "Wait min",
    "ns_per_day": "ns/day",
    "cpu_stall_percent": "CPU stall %",
    "oom_kills": "OOM",
    "outcome": "Outcome",
}
# Job, user, engine, and start time are left-aligned.
JOB_NAME_COLUMNS = 4


@dataclass
class OwnerUsage:
    """One owner's totals over a period."""

    owner: str | None
    owner_namespace: str | None
    jobs: int = 0
    cpu_core_hours: float = 0.0
    gpu_hours: float = 0.0
    memory_gib_hours: float = 0.0
    # Measured jobs that ended in the period, each over its whole window.
    measured_cpu_core_hours: float = 0.0
    used_cpu_core_hours: float = 0.0
    measured_gpu_hours: float = 0.0
    busy_gpu_hours: float = 0.0
    # Jobs that started in the period, from submission to pod start.
    waited_jobs: int = 0
    queue_wait_seconds: float = 0.0
    # Measured jobs that ended in the period, counting only those that reported each value.
    stall_window_seconds: float = 0.0
    cpu_stall_seconds: float = 0.0
    diagnosed_jobs: int = 0
    oom_kills: int = 0
    gpu_energy_jobs: int = 0
    gpu_energy_joules: float = 0.0

    @property
    def cpu_used_percent(self) -> float | None:
        """Share of the measured jobs' CPU allocation they used."""
        return _percent(self.used_cpu_core_hours, self.measured_cpu_core_hours)

    @property
    def gpu_busy_percent(self) -> float | None:
        """Share of the measured jobs' GPU time the GPUs were busy."""
        return _percent(self.busy_gpu_hours, self.measured_gpu_hours)

    @property
    def avg_queue_wait_minutes(self) -> float | None:
        """Mean time from submission to pod start."""
        return self.queue_wait_seconds / self.waited_jobs / SECONDS_PER_MINUTE if self.waited_jobs else None

    @property
    def cpu_stall_percent(self) -> float | None:
        """Share of the measured containers' lifetime that tasks waited for CPU."""
        return _percent(self.cpu_stall_seconds, self.stall_window_seconds)

    @property
    def measured_oom_kills(self) -> int | None:
        """OOM kills in the measured jobs that reported them."""
        return self.oom_kills if self.diagnosed_jobs else None

    @property
    def gpu_energy_kwh(self) -> float | None:
        """GPU energy of the measured jobs that sampled power draw."""
        return self.gpu_energy_joules / JOULES_PER_KWH if self.gpu_energy_jobs else None


@dataclass(frozen=True)
class MeasuredSeconds:
    """A finished job's measurement against its whole window, which the measurement covers."""

    cpu_core_seconds_allocated: float
    cpu_core_seconds_used: float
    gpu_seconds_allocated: float
    gpu_seconds_busy: float
    # The container's lifetime and CPU stall time, when it reported stall time.
    stall_window_seconds: float = 0.0
    cpu_stall_seconds: float = 0.0
    oom_kills: int | None = None
    gpu_energy_joules: float | None = None


def _percent(part: float | None, whole: float | None) -> float | None:
    return None if part is None or not whole else 100 * part / whole


def _utc(value: datetime) -> datetime:
    """SQLite returns naive datetimes; the ledger writes UTC."""
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value


def allocated_seconds(record: MdrunUsage, since: datetime, until: datetime, now: datetime) -> float:
    """Seconds of the job's allocation window inside ``[since, until)``; an open window runs until ``now``."""
    if record.started_at is None:
        return 0.0
    start = max(_utc(record.started_at), since)
    end = min(_utc(record.finished_at) if record.finished_at else now, until)
    return max((end - start).total_seconds(), 0.0)


def queue_wait_seconds(record: MdrunUsage, now: datetime) -> float | None:
    """Submission to pod start; None for jobs that never held resources."""
    if record.started_at is None or not allocated_seconds(record, EPOCH, now, now):
        return None
    return max((_utc(record.started_at) - _utc(record.created_at)).total_seconds(), 0.0)


def container_seconds(measurement: MdrunUsageMeasurement) -> float | None:
    """How long the simulation container had run at its measurement, by its own clock."""
    if measurement.container_started_at is None or measurement.measured_at is None:
        return None
    return max((_utc(measurement.measured_at) - _utc(measurement.container_started_at)).total_seconds(), 0.0)


def measured_seconds(record: MdrunUsage, now: datetime) -> MeasuredSeconds | None:
    """Weigh a finished job's measurement against its whole window; None without a measurement."""
    measurement = record.measurement
    if measurement is None or record.finished_at is None:
        return None
    seconds = allocated_seconds(record, EPOCH, now, now)
    used = measurement.cpu_core_seconds
    utilization = measurement.gpu_utilization if record.gpus else None
    lifetime = container_seconds(measurement)
    stalled = measurement.cpu_stall_seconds if lifetime else None
    power = measurement.gpu_power_watts if record.gpus and lifetime else None
    return MeasuredSeconds(
        cpu_core_seconds_allocated=0.0 if used is None else record.cpu_cores * seconds,
        cpu_core_seconds_used=used or 0.0,
        gpu_seconds_allocated=0.0 if utilization is None else record.gpus * seconds,
        gpu_seconds_busy=0.0 if utilization is None else record.gpus * seconds * utilization / 100,
        stall_window_seconds=0.0 if stalled is None else lifetime or 0.0,
        cpu_stall_seconds=stalled or 0.0,
        oom_kills=measurement.oom_kills,
        gpu_energy_joules=None if power is None else power * record.gpus * (lifetime or 0.0),
    )


def _add_measurement(row: OwnerUsage, measured: MeasuredSeconds) -> None:
    row.measured_cpu_core_hours += measured.cpu_core_seconds_allocated / SECONDS_PER_HOUR
    row.used_cpu_core_hours += measured.cpu_core_seconds_used / SECONDS_PER_HOUR
    row.measured_gpu_hours += measured.gpu_seconds_allocated / SECONDS_PER_HOUR
    row.busy_gpu_hours += measured.gpu_seconds_busy / SECONDS_PER_HOUR
    row.stall_window_seconds += measured.stall_window_seconds
    row.cpu_stall_seconds += measured.cpu_stall_seconds
    if measured.oom_kills is not None:
        row.diagnosed_jobs += 1
        row.oom_kills += measured.oom_kills
    if measured.gpu_energy_joules is not None:
        row.gpu_energy_jobs += 1
        row.gpu_energy_joules += measured.gpu_energy_joules


def summarize(records: Iterable[MdrunUsage], since: datetime, until: datetime, now: datetime) -> list[OwnerUsage]:
    """
    Totals per owner, with each allocation window clipped to ``[since, until)``.

    Open windows run until ``now``; jobs that never started count nothing. Queue wait covers jobs that started in
    the period. Efficiency and diagnostics cover measured jobs that ended in the period, each over its whole window.

    Returns:
        Owners by GPU-hours, then CPU core-hours, descending.
    """
    totals: dict[tuple[str | None, str | None], OwnerUsage] = {}
    for record in records:
        hours = allocated_seconds(record, since, until, now) / SECONDS_PER_HOUR
        if not hours:
            continue

        key = (record.owner, record.owner_namespace)
        row = totals.setdefault(key, OwnerUsage(*key))
        row.jobs += 1
        row.cpu_core_hours += record.cpu_cores * hours
        row.gpu_hours += record.gpus * hours
        row.memory_gib_hours += record.memory_gib * hours
        started_in_period = record.started_at is not None and since <= _utc(record.started_at) < until
        if started_in_period and (wait := queue_wait_seconds(record, now)) is not None:
            row.waited_jobs += 1
            row.queue_wait_seconds += wait
        ended_in_period = record.finished_at is not None and since <= _utc(record.finished_at) < until
        if ended_in_period and (measured := measured_seconds(record, now)):
            _add_measurement(row, measured)
    return sorted(totals.values(), key=lambda row: (row.gpu_hours, row.cpu_core_hours), reverse=True)


def jobs_in_period(records: Iterable[MdrunUsage], since: datetime, until: datetime, now: datetime) -> list[MdrunUsage]:
    """Jobs whose allocation window overlaps ``[since, until)``, by start time."""
    return sorted(
        (record for record in records if allocated_seconds(record, since, until, now)),
        key=lambda record: _utc(record.started_at or EPOCH),
    )


def estimated_cost(row: OwnerUsage) -> float | None:
    """Cost at the configured hourly rates; None when any rate is unset."""
    if COST_CPU_CORE_HOUR is None or COST_GPU_HOUR is None or COST_GB_RAM_HOUR is None:
        return None
    return (
        row.cpu_core_hours * COST_CPU_CORE_HOUR
        + row.gpu_hours * COST_GPU_HOUR
        + row.memory_gib_hours * COST_GB_RAM_HOUR
    )


def _optional(value: float | None, spec: str) -> str:
    return "" if value is None else format(value, spec)


def _percent_cell(value: float | None) -> str:
    return "-" if value is None else f"{value:.0f}%"


def _minutes(seconds: float | None) -> float | None:
    return None if seconds is None else seconds / SECONDS_PER_MINUTE


def _gib(size: int | None) -> float | None:
    return None if size is None else size / 2**30


def _diagnostic_cells(record: MdrunUsage, measurement: MdrunUsageMeasurement | None) -> dict[str, str]:
    """Format a job's measured diagnostics; stall and throttling are shares of the container's lifetime."""
    if measurement is None:
        return dict.fromkeys(JOB_CSV_COLUMNS[JOB_CSV_COLUMNS.index("startup_minutes") :], "")
    lifetime = container_seconds(measurement)
    startup = None
    if measurement.container_started_at is not None and record.started_at is not None:
        startup = max((_utc(measurement.container_started_at) - _utc(record.started_at)).total_seconds(), 0.0)
    return {
        "startup_minutes": _optional(_minutes(startup), ".1f"),
        "ns_per_day": _optional(measurement.ns_per_day, ".2f"),
        "cpu_throttled_percent": _optional(_percent(measurement.cpu_throttled_seconds, lifetime), ".1f"),
        "cpu_stall_percent": _optional(_percent(measurement.cpu_stall_seconds, lifetime), ".1f"),
        "memory_stall_percent": _optional(_percent(measurement.memory_stall_seconds, lifetime), ".1f"),
        "io_stall_percent": _optional(_percent(measurement.io_stall_seconds, lifetime), ".1f"),
        "oom_kills": "" if measurement.oom_kills is None else str(measurement.oom_kills),
        "io_read_gib": _optional(_gib(measurement.io_read_bytes), ".2f"),
        "io_write_gib": _optional(_gib(measurement.io_write_bytes), ".2f"),
        "gpu_power_watts": _optional(measurement.gpu_power_watts, ".1f"),
    }


def _job_cells(record: MdrunUsage, now: datetime) -> dict[str, str]:
    """One job's report cells, keyed like ``JOB_CSV_COLUMNS``; empty where nothing was measured."""
    measurement = record.measurement
    measured = measured_seconds(record, now)
    cpu_used = gpu_busy = memory_peak = gpu_memory_peak = None
    if measured is not None:
        cpu_used = _percent(measured.cpu_core_seconds_used, measured.cpu_core_seconds_allocated)
        gpu_busy = _percent(measured.gpu_seconds_busy, measured.gpu_seconds_allocated)
    if measurement is not None:
        memory_peak, gpu_memory_peak = measurement.memory_peak_gib, measurement.gpu_memory_peak_gib
    return {
        "job_id": record.job_id,
        "user": record.owner or "",
        "namespace": record.owner_namespace or "",
        "engine": record.engine,
        "outcome": record.outcome.value if record.outcome else "",
        "started_at": f"{_utc(record.started_at or EPOCH):%Y-%m-%d %H:%M}",
        "hours": f"{allocated_seconds(record, EPOCH, now, now) / SECONDS_PER_HOUR:.2f}",
        "cpu_cores": str(record.cpu_cores),
        "cpu_used_percent": _optional(cpu_used, ".1f"),
        "memory_gib": str(record.memory_gib),
        "memory_peak_gib": _optional(memory_peak, ".1f"),
        "gpus": str(record.gpus),
        "gpu_busy_percent": _optional(gpu_busy, ".1f"),
        "gpu_memory_peak_gib": _optional(gpu_memory_peak, ".1f"),
        "measured_to_exit": "" if measurement is None else ("yes" if measurement.complete else "no"),
        "queue_wait_minutes": _optional(_minutes(queue_wait_seconds(record, now)), ".1f"),
        **_diagnostic_cells(record, measurement),
    }


def _print_aligned(lines: Sequence[Sequence[str]], left_columns: int) -> None:
    widths = [max(len(line[i]) for line in lines) for i in range(len(lines[0]))]
    for line in lines:
        cells = (cell.ljust(w) if i < left_columns else cell.rjust(w) for i, (cell, w) in enumerate(zip(line, widths)))
        print("  ".join(cells))


def _print_csv(rows: list[OwnerUsage]) -> None:
    writer = csv.writer(sys.stdout, lineterminator="\n")
    writer.writerow([
        "user",
        "namespace",
        "jobs",
        "cpu_core_hours",
        "gpu_hours",
        "memory_gib_hours",
        "cpu_used_percent",
        "gpu_busy_percent",
        "estimated_cost",
        "cpu_stall_percent",
        "oom_kills",
        "gpu_energy_kwh",
        "avg_queue_wait_minutes",
    ])
    for row in rows:
        writer.writerow([
            row.owner or "",
            row.owner_namespace or "",
            row.jobs,
            f"{row.cpu_core_hours:.2f}",
            f"{row.gpu_hours:.2f}",
            f"{row.memory_gib_hours:.2f}",
            _optional(row.cpu_used_percent, ".1f"),
            _optional(row.gpu_busy_percent, ".1f"),
            _optional(estimated_cost(row), ".2f"),
            _optional(row.cpu_stall_percent, ".1f"),
            "" if row.measured_oom_kills is None else row.measured_oom_kills,
            _optional(row.gpu_energy_kwh, ".2f"),
            _optional(row.avg_queue_wait_minutes, ".1f"),
        ])


def _print_table(rows: list[OwnerUsage], since: datetime, until: datetime) -> None:
    print(f"MDRun usage {since:%Y-%m-%d %H:%M} to {until:%Y-%m-%d %H:%M} UTC (requested resources x pod lifetime)")
    if not rows:
        print("No usage in this period.")
        return

    total = OwnerUsage("TOTAL", "", **{field: sum(getattr(row, field) for row in rows) for field in SUMMED_FIELDS})
    lines = [
        (
            "User",
            "Namespace",
            "Jobs",
            "CPU core-h",
            "GPU-h",
            "Mem GiB-h",
            "CPU used",
            "GPU busy",
            "CPU stall",
            "OOM",
            "GPU kWh",
            "Wait min",
            "Est. cost",
        )
    ]
    for row in [*rows, total]:
        lines.append((
            row.owner or "(unattributed)",
            row.owner_namespace or "-",
            str(row.jobs),
            f"{row.cpu_core_hours:.1f}",
            f"{row.gpu_hours:.1f}",
            f"{row.memory_gib_hours:.1f}",
            _percent_cell(row.cpu_used_percent),
            _percent_cell(row.gpu_busy_percent),
            _percent_cell(row.cpu_stall_percent),
            "-" if row.measured_oom_kills is None else str(row.measured_oom_kills),
            _optional(row.gpu_energy_kwh, ".2f") or "-",
            _optional(row.avg_queue_wait_minutes, ".1f") or "-",
            _optional(estimated_cost(row), ".2f") or "-",
        ))
    _print_aligned(lines, NAME_COLUMNS)
    print(
        "CPU used, GPU busy, CPU stall, OOM, and GPU kWh cover jobs that measured themselves and ended in the period."
        " Wait covers jobs that started in it."
    )


def _print_jobs_csv(jobs: list[MdrunUsage], now: datetime) -> None:
    writer = csv.DictWriter(sys.stdout, fieldnames=JOB_CSV_COLUMNS, lineterminator="\n")
    writer.writeheader()
    for record in jobs:
        writer.writerow(_job_cells(record, now))


def _print_jobs_table(jobs: list[MdrunUsage], now: datetime, since: datetime, until: datetime) -> None:
    print(f"MDRun jobs {since:%Y-%m-%d %H:%M} to {until:%Y-%m-%d %H:%M} UTC (hours cover each whole window)")
    if not jobs:
        print("No jobs in this period.")
        return

    lines = [tuple(JOB_TABLE_COLUMNS.values())]
    for record in jobs:
        cells = _job_cells(record, now)
        cells["job_id"] = cells["job_id"][:8]
        cells["user"] = cells["user"] or "(unattributed)"
        lines.append(tuple(cells[column] or "-" for column in JOB_TABLE_COLUMNS))
    _print_aligned(lines, JOB_NAME_COLUMNS)


def _date(value: str) -> datetime:
    """ISO date or datetime; naive values are UTC."""
    return _utc(datetime.fromisoformat(value))


def main(argv: Sequence[str] | None = None) -> None:
    """Print usage per owner, or per job, for a period, by default the current month so far."""
    now = datetime.now(UTC)
    parser = argparse.ArgumentParser(prog="python -m usage", description=__doc__)
    parser.add_argument(
        "--since",
        type=_date,
        default=now.replace(day=1, hour=0, minute=0, second=0, microsecond=0),
        help="period start, inclusive (default: start of this month, UTC)",
    )
    parser.add_argument("--until", type=_date, default=now, help="period end, exclusive (default: now)")
    parser.add_argument("--jobs", action="store_true", help="list jobs with their measured usage")
    parser.add_argument("--csv", action="store_true", help="print CSV instead of a table")
    args = parser.parse_args(argv)

    records = db.session.scalars(select(MdrunUsage).options(selectinload(MdrunUsage.measurement))).all()
    if args.jobs:
        jobs = jobs_in_period(records, since=args.since, until=args.until, now=now)
        if args.csv:
            _print_jobs_csv(jobs, now)
        else:
            _print_jobs_table(jobs, now, args.since, args.until)
        return

    rows = summarize(records, since=args.since, until=args.until, now=now)
    if args.csv:
        _print_csv(rows)
    else:
        _print_table(rows, args.since, args.until)


if __name__ == "__main__":
    # Importing app builds the Flask app (database, Kubernetes config), which only the CLI needs.
    from app import app as flask_app

    with flask_app.app_context():
        main()
