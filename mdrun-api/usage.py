"""
Per-user MDRun usage from the ledger: ``python -m usage [--since DATE] [--until DATE] [--csv]``.

Usage is allocation: the CPU cores, memory, and GPUs a job requested, times how long its pod held them.
"""

import argparse
import csv
import sys
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime

from config import COST_CPU_CORE_HOUR, COST_GB_RAM_HOUR, COST_GPU_HOUR
from extensions import db
from models import MdrunUsage
from sqlalchemy import select

SECONDS_PER_HOUR = 3600
# User and namespace columns are left-aligned; the numbers after them right-aligned.
NAME_COLUMNS = 2


@dataclass
class OwnerUsage:
    """One owner's totals over a period."""

    owner: str | None
    owner_namespace: str | None
    jobs: int = 0
    cpu_core_hours: float = 0.0
    gpu_hours: float = 0.0
    memory_gib_hours: float = 0.0


def _utc(value: datetime) -> datetime:
    """SQLite returns naive datetimes; the ledger writes UTC."""
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value


def summarize(records: Iterable[MdrunUsage], since: datetime, until: datetime, now: datetime) -> list[OwnerUsage]:
    """
    Totals per owner, with each allocation window clipped to ``[since, until)``.

    Open windows run until ``now``; jobs that never started count nothing.

    Returns:
        Owners by GPU-hours, then CPU core-hours, descending.
    """
    totals: dict[tuple[str | None, str | None], OwnerUsage] = {}
    for record in records:
        if record.started_at is None:
            continue
        start = max(_utc(record.started_at), since)
        end = min(_utc(record.finished_at) if record.finished_at else now, until)
        hours = (end - start).total_seconds() / SECONDS_PER_HOUR
        if hours <= 0:
            continue

        key = (record.owner, record.owner_namespace)
        row = totals.setdefault(key, OwnerUsage(*key))
        row.jobs += 1
        row.cpu_core_hours += record.cpu_cores * hours
        row.gpu_hours += record.gpus * hours
        row.memory_gib_hours += record.memory_gib * hours
    return sorted(totals.values(), key=lambda row: (row.gpu_hours, row.cpu_core_hours), reverse=True)


def estimated_cost(row: OwnerUsage) -> float | None:
    """Cost at the configured hourly rates; None when any rate is unset."""
    if COST_CPU_CORE_HOUR is None or COST_GPU_HOUR is None or COST_GB_RAM_HOUR is None:
        return None
    return (
        row.cpu_core_hours * COST_CPU_CORE_HOUR
        + row.gpu_hours * COST_GPU_HOUR
        + row.memory_gib_hours * COST_GB_RAM_HOUR
    )


def _print_csv(rows: list[OwnerUsage]) -> None:
    writer = csv.writer(sys.stdout, lineterminator="\n")
    writer.writerow(["user", "namespace", "jobs", "cpu_core_hours", "gpu_hours", "memory_gib_hours", "estimated_cost"])
    for row in rows:
        cost = estimated_cost(row)
        writer.writerow([
            row.owner or "",
            row.owner_namespace or "",
            row.jobs,
            f"{row.cpu_core_hours:.2f}",
            f"{row.gpu_hours:.2f}",
            f"{row.memory_gib_hours:.2f}",
            "" if cost is None else f"{cost:.2f}",
        ])


def _print_table(rows: list[OwnerUsage], since: datetime, until: datetime) -> None:
    print(f"MDRun usage {since:%Y-%m-%d %H:%M} to {until:%Y-%m-%d %H:%M} UTC (requested resources x pod lifetime)")
    if not rows:
        print("No usage in this period.")
        return

    total = OwnerUsage(
        "TOTAL",
        "",
        sum(row.jobs for row in rows),
        sum(row.cpu_core_hours for row in rows),
        sum(row.gpu_hours for row in rows),
        sum(row.memory_gib_hours for row in rows),
    )
    header = ("User", "Namespace", "Jobs", "CPU core-h", "GPU-h", "Mem GiB-h", "Est. cost")
    lines = [header]
    for row in [*rows, total]:
        cost = estimated_cost(row)
        lines.append((
            row.owner or "(unattributed)",
            row.owner_namespace or "-",
            str(row.jobs),
            f"{row.cpu_core_hours:.1f}",
            f"{row.gpu_hours:.1f}",
            f"{row.memory_gib_hours:.1f}",
            "-" if cost is None else f"{cost:.2f}",
        ))
    widths = [max(len(line[i]) for line in lines) for i in range(len(header))]
    for line in lines:
        cells = (cell.ljust(w) if i < NAME_COLUMNS else cell.rjust(w) for i, (cell, w) in enumerate(zip(line, widths)))
        print("  ".join(cells))


def _date(value: str) -> datetime:
    """ISO date or datetime; naive values are UTC."""
    return _utc(datetime.fromisoformat(value))


def main(argv: Sequence[str] | None = None) -> None:
    """Print usage per owner for a period, by default the current month so far."""
    now = datetime.now(UTC)
    parser = argparse.ArgumentParser(prog="python -m usage", description=__doc__)
    parser.add_argument(
        "--since",
        type=_date,
        default=now.replace(day=1, hour=0, minute=0, second=0, microsecond=0),
        help="period start, inclusive (default: start of this month, UTC)",
    )
    parser.add_argument("--until", type=_date, default=now, help="period end, exclusive (default: now)")
    parser.add_argument("--csv", action="store_true", help="print CSV instead of a table")
    args = parser.parse_args(argv)

    records = db.session.scalars(select(MdrunUsage)).all()
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
