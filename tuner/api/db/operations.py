"""Database operations for the MD tuner."""

import logging
from datetime import datetime, timezone

from sqlalchemy import asc, select
from sqlalchemy.orm.exc import StaleDataError

from api.db.models import Job, Trial, get_session
from api.schemas.common import JobStatus, MDEngine

logger = logging.getLogger(__name__)


def create_job(job_id: str, engine: MDEngine) -> None:
    """Create a new job record with PENDING status."""
    with get_session() as session:
        session.add(Job(id=job_id, engine=engine, status=JobStatus.PENDING))
        session.commit()


def update_job_status(job_id: str, status: JobStatus, error: str | None = None) -> bool:
    """Update a job's status and optional error message."""
    with get_session() as session:
        if job := session.execute(select(Job).where(Job.id == job_id)).scalar_one_or_none():
            job.status, job.error, job.updated_at = status, error, datetime.now(timezone.utc)
            session.commit()
            return True
        return False


def get_job(job_id: str) -> Job | None:
    """Fetch a job by ID, or None if not found."""
    with get_session() as session:
        return session.execute(select(Job).where(Job.id == job_id)).scalar_one_or_none()


def delete_job(job_id: str) -> bool:
    """Delete a job and its cascaded trials; returns True if found and deleted."""
    with get_session() as session:
        if job := session.execute(select(Job).where(Job.id == job_id)).scalar_one_or_none():
            session.delete(job)
            session.commit()
            return True
        return False


def create_trial_result(
    job_id: str,
    config_json: dict,
    status: JobStatus,
    performance: float | None,
) -> int:
    """Create a trial result. Returns the database trial ID."""
    with get_session() as session:
        trial = Trial(job_id=job_id, config_json=config_json, status=status, performance=performance)
        session.add(trial)
        session.commit()
        session.refresh(trial)
        return trial.id


def update_trial_result(trial_id: int, status: JobStatus, performance: float | None) -> bool:
    """Update a trial's status and performance; returns True if found and updated."""
    with get_session() as session:
        if trial := session.execute(select(Trial).where(Trial.id == trial_id)).scalar_one_or_none():
            trial.status, trial.performance = status, performance
            try:
                session.commit()
            except StaleDataError:
                session.rollback()
                logger.info("Trial %d disappeared before result update committed", trial_id)
                return False
            return True
        return False


def get_trial(trial_id: int, job_id: str) -> Trial | None:
    """Fetch a single trial by ID, scoped to a job. Returns None if not found."""
    with get_session() as session:
        return session.execute(select(Trial).where(Trial.id == trial_id, Trial.job_id == job_id)).scalar_one_or_none()


def get_trials_by_job_id(job_id: str) -> list[Trial]:
    """Get all trials for a job as raw Trial ORM objects."""
    with get_session() as session:
        return list(
            session.execute(select(Trial).where(Trial.job_id == job_id).order_by(asc(Trial.id))).scalars().all()
        )
