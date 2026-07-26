"""Database connection and ORM models."""

from datetime import datetime, timezone
from typing import Any, Protocol

from sqlalchemy import JSON, Enum, ForeignKey, String, create_engine, event
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, relationship, sessionmaker

from api.config import DB_PATH
from api.schemas.common import JobStatus, MDEngine


class Base(DeclarativeBase):
    """SQLAlchemy declarative base for all ORM models."""


class Job(Base):
    """Tuning job record tracking engine, status, and associated trials."""

    __tablename__ = "jobs"

    id: Mapped[str] = mapped_column(String, primary_key=True, nullable=False)
    engine: Mapped[MDEngine] = mapped_column(Enum(MDEngine, native_enum=False), nullable=False, index=True)
    status: Mapped[JobStatus] = mapped_column(Enum(JobStatus, native_enum=False), nullable=False, index=True)
    error: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    trials: Mapped[list["Trial"]] = relationship(
        "Trial", back_populates="job", cascade="all, delete-orphan", passive_deletes=True
    )


class Trial(Base):
    """Individual trial result within a tuning job."""

    __tablename__ = "trials"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    job_id: Mapped[str] = mapped_column(String, ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False, index=True)
    config_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    status: Mapped[JobStatus] = mapped_column(Enum(JobStatus, native_enum=False), nullable=False)
    performance: Mapped[float | None] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=lambda: datetime.now(timezone.utc))

    job: Mapped["Job"] = relationship("Job", back_populates="trials")


class _DBAPICursor(Protocol):
    def execute(self, statement: str) -> object: ...

    def close(self) -> None: ...


class _DBAPIConnection(Protocol):
    def cursor(self) -> _DBAPICursor: ...


def _set_sqlite_pragmas(dbapi_conn: _DBAPIConnection, _connection_record: object) -> None:
    cursor = dbapi_conn.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA busy_timeout=5000")
    cursor.close()


_engine = create_engine(
    f"sqlite:///{DB_PATH}",
    connect_args={"check_same_thread": False, "timeout": 5.0},
    pool_pre_ping=True,
)

event.listen(_engine, "connect", _set_sqlite_pragmas)

SessionLocal = sessionmaker(bind=_engine, expire_on_commit=False)


def get_session() -> Session:
    """Return a new database session."""
    return SessionLocal()


def init_db() -> None:
    """Create database tables and parent directories if they do not exist."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    Base.metadata.create_all(_engine)
