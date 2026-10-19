"""Unit tests for experiment archive/restore lifecycle."""

import logging
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, Mock, patch

import pytest
from core.enums import AmberBinary, AnalysisType, DeviceType, Engine, EwaldPreset, JobStatus
from core.errors import ApiError, Conflict
from modules.archive.status import ArchiveDirection, ArchiveState, ArchiveStatus, write_status
from modules.archive.submission import SubmissionError
from modules.experiments.schemas import Experiment as ExperimentOut
from modules.models import AmberJob, AnalysisJob, Experiment, GromacsJob, Notebook
from sqlalchemy.ext.asyncio import AsyncSession

EXP_ID = "abcde"


async def _reload(db_session: AsyncSession) -> Experiment:
    """Commit, then load the experiment fresh (with its jobs) the way a request would."""
    await db_session.commit()
    db_session.expunge_all()
    experiment = await db_session.get(Experiment, EXP_ID)
    assert experiment is not None
    return experiment


@pytest.fixture
async def experiment(db_session: AsyncSession, tmp_path: Path) -> Experiment:
    db_session.add(Experiment(id=EXP_ID, name="test", engine=Engine.GMX))
    db_session.add(Notebook(experiment_id=EXP_ID))
    (tmp_path / EXP_ID).mkdir()
    return await _reload(db_session)


@pytest.fixture
def s3() -> Iterator[None]:
    with patch("modules.experiments.models.S3_BUCKET", "test-bucket"):
        yield


def _job_active(live: bool) -> Any:
    return patch("modules.archive.submission.is_job_active", AsyncMock(return_value=live))


def _submit_ok(_direction: str, _experiment_id: str, _data_dir: Path) -> str:
    return "attempt-1"


class TestArchiveGates:
    async def test_no_s3_config_400(self, experiment: Experiment, db_session: AsyncSession) -> None:
        with patch("modules.experiments.models.S3_BUCKET", ""), pytest.raises(ApiError) as exc_info:
            await experiment.archive(db_session)
        assert exc_info.value.status_code == 400

    async def test_live_simulation_job_409(self, experiment: Experiment, db_session: AsyncSession) -> None:
        db_session.add(
            GromacsJob(
                id="job-1",
                experiment_id=EXP_ID,
                engine=Engine.GMX,
                simulation_path="x.simulation.json",
                np=1,
                ntomp=1,
                pme=DeviceType.CPU,
                nb=DeviceType.CPU,
            )
        )
        experiment = await _reload(db_session)
        with (
            patch("modules.experiments.models.S3_BUCKET", "test-bucket"),
            patch("modules.jobs.gmx.models.mdrun.get_gmx_job", AsyncMock(return_value={"status": "RUNNING"})),
            pytest.raises(ApiError) as exc_info,
        ):
            await experiment.archive(db_session)
        assert exc_info.value.problem_type == "urn:mddash:archive-conflict"

    async def test_active_upload_409(self, experiment: Experiment, db_session: AsyncSession) -> None:
        with (
            patch("modules.experiments.models.S3_BUCKET", "test-bucket"),
            patch("modules.experiments.models.read_status", return_value=Mock(state="running")),
            patch("modules.experiments.models.is_upload_active", AsyncMock(return_value=True)),
            pytest.raises(ApiError) as exc_info,
        ):
            await experiment.archive(db_session)
        assert exc_info.value.problem_type == "urn:mddash:archive-conflict"

    async def test_already_archived_409(self, experiment: Experiment, db_session: AsyncSession, s3: None) -> None:
        experiment.archived_at = datetime.now(UTC)
        with _job_active(False), pytest.raises(ApiError) as exc_info:
            await experiment.archive(db_session)
        assert exc_info.value.problem_type == "urn:mddash:archive-conflict"

    async def test_running_notebook_is_stopped(
        self, experiment: Experiment, db_session: AsyncSession, s3: None
    ) -> None:
        with (
            patch.object(Notebook, "stop") as mock_stop,
            patch("modules.experiments.models.archive_submission.submit_job", side_effect=_submit_ok),
        ):
            await experiment.archive(db_session)
        mock_stop.assert_called_once()


class TestArchiveSubmit:
    async def test_snapshots_and_submit(self, experiment: Experiment, db_session: AsyncSession, s3: None) -> None:
        with patch("modules.experiments.models.archive_submission.submit_job", side_effect=_submit_ok) as mock_submit:
            attempt = await experiment.archive(db_session)
        assert attempt == "attempt-1"
        mock_submit.assert_called_once()
        direction, exp_id, _ = mock_submit.call_args[0]
        assert direction == ArchiveDirection.ARCHIVE.value
        assert exp_id == EXP_ID

        stored = await _reload(db_session)
        assert stored.archived_step is not None
        assert stored.archived_status is not None
        assert stored.archived_at is None  # set by reconciliation after local deletion


class TestRestoreGates:
    async def test_not_archived_409(self, experiment: Experiment, s3: None) -> None:
        with pytest.raises(ApiError) as exc_info:
            await experiment.restore()
        assert exc_info.value.problem_type == "urn:mddash:archive-conflict"

    async def test_existing_dir_409(self, experiment: Experiment, s3: None) -> None:
        experiment.archived_at = datetime.now(UTC)
        with _job_active(False), pytest.raises(ApiError) as exc_info:
            await experiment.restore()
        assert exc_info.value.problem_type == "urn:mddash:archive-conflict"

    @pytest.mark.parametrize("state", [ArchiveState.FAILED, ArchiveState.RUNNING], ids=["failed", "stale-running"])
    async def test_retry_after_failed_restore(
        self, experiment: Experiment, s3: None, tmp_path: Path, state: ArchiveState
    ) -> None:
        """A failed restore (or one whose Job died mid-run) leaves dir + doc; that doc is the retry sentinel."""
        experiment.archived_at = datetime.now(UTC)
        write_status(ArchiveStatus(attempt_id="a", state=state.value, direction="restore"), EXP_ID, tmp_path)
        with (
            _job_active(False),
            patch("modules.experiments.models.archive_submission.submit_job", side_effect=_submit_ok) as mock_submit,
        ):
            assert await experiment.restore() == "attempt-1"
        mock_submit.assert_called_once()

    async def test_happy_path(self, experiment: Experiment, s3: None, tmp_path: Path) -> None:
        experiment.archived_at = datetime.now(UTC)
        (tmp_path / EXP_ID).rmdir()
        with (
            _job_active(False),
            patch("modules.experiments.models.archive_submission.submit_job", side_effect=_submit_ok) as mock_submit,
        ):
            attempt = await experiment.restore()
        assert attempt == "attempt-1"
        assert mock_submit.call_args[0][0] == ArchiveDirection.RESTORE.value


class TestArchiveStateReconciliation:
    def _snap(self, experiment: Experiment) -> None:
        experiment.archived_step = 2
        experiment.archived_status = "running"
        experiment.archived_size_bytes = 1234

    async def test_plain_experiment_no_io(self, experiment: Experiment) -> None:
        """No markers -> None without touching disk or K8s."""
        with patch("modules.experiments.models.archive_submission.is_job_active") as mock_active:
            assert await experiment.refresh_archive_state() is None
            assert experiment.archive_state is None
        mock_active.assert_not_called()

    async def test_archiving_while_job_live(self, experiment: Experiment) -> None:
        self._snap(experiment)
        with _job_active(True):
            assert await experiment.refresh_archive_state() == "archiving"

    async def test_archived_after_dir_deleted(
        self, experiment: Experiment, db_session: AsyncSession, tmp_path: Path
    ) -> None:
        self._snap(experiment)
        (tmp_path / EXP_ID).rmdir()
        with _job_active(False):
            assert await experiment.refresh_archive_state() == "archived"
        assert experiment.archived_at is not None
        assert (await _reload(db_session)).archived_at is not None

    @pytest.mark.parametrize(
        "doc_state", [ArchiveState.FAILED, ArchiveState.RUNNING, None], ids=["failed-doc", "dead-job", "no-doc"]
    )
    async def test_archive_failed(self, experiment: Experiment, tmp_path: Path, doc_state: ArchiveState | None) -> None:
        """A FAILED doc, or any in-flight state without a live Job (evicted, backoffLimit 0), is archive_failed."""
        self._snap(experiment)
        if doc_state is not None:
            write_status(ArchiveStatus(attempt_id="a", state=doc_state.value, direction="archive"), EXP_ID, tmp_path)
        with _job_active(False):
            assert await experiment.refresh_archive_state() == "archive_failed"

    async def test_job_liveness_cached_across_reads(self, experiment: Experiment) -> None:
        """List serialization must not fan out K8s reads per experiment per request."""
        self._snap(experiment)
        with _job_active(False) as mock_active:
            assert await experiment.refresh_archive_state() == "archive_failed"
            assert await experiment.refresh_archive_state() == "archive_failed"
        assert mock_active.call_count == 1

    async def test_archived_baseline(self, experiment: Experiment, tmp_path: Path) -> None:
        experiment.archived_at = datetime.now(UTC)
        (tmp_path / EXP_ID).rmdir()
        with _job_active(False):
            assert await experiment.refresh_archive_state() == "archived"

    async def test_restoring(self, experiment: Experiment, tmp_path: Path) -> None:
        experiment.archived_at = datetime.now(UTC)
        write_status(
            ArchiveStatus(attempt_id="a", state=ArchiveState.RUNNING.value, direction="restore"), EXP_ID, tmp_path
        )
        with _job_active(True):
            assert await experiment.refresh_archive_state() == "restoring"

    async def test_restore_completion_clears_flags(
        self, experiment: Experiment, db_session: AsyncSession, tmp_path: Path
    ) -> None:
        experiment.archived_at = datetime.now(UTC)
        self._snap(experiment)
        experiment = await _reload(db_session)
        write_status(
            ArchiveStatus(attempt_id="a", state=ArchiveState.COMPLETED.value, direction="restore"), EXP_ID, tmp_path
        )
        with _job_active(False):
            assert await experiment.refresh_archive_state() is None
        stored = await _reload(db_session)
        assert stored.archived_at is None
        assert stored.archived_step is None
        assert stored.archived_size_bytes is None

    async def test_restore_failed(self, experiment: Experiment, tmp_path: Path) -> None:
        experiment.archived_at = datetime.now(UTC)
        write_status(
            ArchiveStatus(attempt_id="a", state=ArchiveState.FAILED.value, direction="restore", reason="copy"),
            EXP_ID,
            tmp_path,
        )
        with _job_active(False):
            assert await experiment.refresh_archive_state() == "restore_failed"

    async def test_live_job_outranks_failed_sentinel(self, experiment: Experiment, tmp_path: Path) -> None:
        """A retried restore reads as restoring once its Job exists, not when the worker rewrites the doc."""
        experiment.archived_at = datetime.now(UTC)
        write_status(
            ArchiveStatus(attempt_id="a", state=ArchiveState.FAILED.value, direction="restore", reason="copy"),
            EXP_ID,
            tmp_path,
        )
        with _job_active(True):
            assert await experiment.refresh_archive_state() == "restoring"

    async def test_stale_running_restore_doc_is_failed(self, experiment: Experiment, tmp_path: Path) -> None:
        """An in-flight restore doc with no live Job (evicted, backoffLimit 0) is failed, as in the archive direction."""
        experiment.archived_at = datetime.now(UTC)
        write_status(
            ArchiveStatus(attempt_id="a", state=ArchiveState.RUNNING.value, direction="restore"), EXP_ID, tmp_path
        )
        with _job_active(False):
            assert await experiment.refresh_archive_state() == "restore_failed"

    async def test_property_serves_one_reconciliation(self, experiment: Experiment) -> None:
        """Serialization reads the refreshed value, so archived_at and archive_state come from one reconciliation."""
        self._snap(experiment)
        with patch.object(Experiment, "_read_archive_state", AsyncMock(return_value="archiving")) as mock_read:
            await experiment.refresh_archive_state()
            assert experiment.archive_state == "archiving"
            assert experiment.archive_state == "archiving"
        assert mock_read.call_count == 1

    def test_reading_marked_state_before_refresh_fails_loudly(self, experiment: Experiment) -> None:
        self._snap(experiment)
        with pytest.raises(RuntimeError, match="before refresh_archive_state"):
            _ = experiment.archive_state


class TestSubmissionFailure:
    async def test_archive_submit_failure_409_problem(
        self, experiment: Experiment, db_session: AsyncSession, s3: None
    ) -> None:
        with (
            patch(
                "modules.experiments.models.archive_submission.submit_job",
                side_effect=SubmissionError("object is being deleted"),
            ),
            pytest.raises(ApiError) as exc_info,
        ):
            await experiment.archive(db_session)
        assert exc_info.value.status_code == 409
        assert exc_info.value.problem_type == "urn:mddash:archive-submission-failed"

    async def test_restore_submit_failure_409_problem(self, experiment: Experiment, s3: None, tmp_path: Path) -> None:
        experiment.archived_at = datetime.now(UTC)
        (tmp_path / EXP_ID).rmdir()
        with (
            _job_active(False),
            patch(
                "modules.experiments.models.archive_submission.submit_job",
                side_effect=SubmissionError("object is being deleted"),
            ),
            pytest.raises(ApiError) as exc_info,
        ):
            await experiment.restore()
        assert exc_info.value.status_code == 409
        assert exc_info.value.problem_type == "urn:mddash:archive-submission-failed"


class TestDeleteWithArchive:
    async def test_archived_delete_purges(self, experiment: Experiment, tmp_path: Path) -> None:
        experiment.archived_at = datetime.now(UTC)
        (tmp_path / EXP_ID).rmdir()
        with (
            patch("modules.experiments.models.archive_submission.delete_jobs") as mock_delete,
            patch("modules.experiments.models.archive_submission.submit_purge_job") as mock_purge,
            patch.object(Notebook, "stop"),
        ):
            await experiment.delete()
        mock_delete.assert_called_once_with(EXP_ID)
        mock_purge.assert_called_once_with(EXP_ID)

    async def test_active_delete_no_purge(self, experiment: Experiment) -> None:
        with (
            patch("modules.experiments.models.archive_submission.delete_jobs"),
            patch("modules.experiments.models.archive_submission.submit_purge_job") as mock_purge,
            patch.object(Notebook, "stop"),
        ):
            await experiment.delete()
        mock_purge.assert_not_called()


class TestDeleteAnalysisJobs:
    async def _with_analysis_job(self, db_session: AsyncSession) -> Experiment:
        db_session.add(
            AnalysisJob(
                id="abc123def456",
                experiment_id=EXP_ID,
                simulation_path="production/md.simulation.json",
                analysis_name=AnalysisType.RMSDS,
                trajectory_file="production/md.xtc",
            )
        )
        return await _reload(db_session)

    async def test_delete_removes_analysis_jobs(self, experiment: Experiment, db_session: AsyncSession) -> None:
        experiment = await self._with_analysis_job(db_session)
        with (
            patch("modules.experiments.models.archive_submission.delete_jobs"),
            patch("modules.experiments.models.archive_submission.submit_purge_job"),
            patch.object(Notebook, "stop"),
            patch.object(AnalysisJob, "delete") as mock_delete,
        ):
            await experiment.delete()
        mock_delete.assert_called_once_with()

    async def test_failing_analysis_delete_does_not_abort(
        self, experiment: Experiment, db_session: AsyncSession
    ) -> None:
        experiment = await self._with_analysis_job(db_session)
        with (
            patch("modules.experiments.models.archive_submission.delete_jobs"),
            patch("modules.experiments.models.archive_submission.submit_purge_job") as mock_purge,
            patch.object(Notebook, "stop"),
            patch.object(AnalysisJob, "delete", side_effect=RuntimeError("k8s down")),
        ):
            await experiment.delete()
        mock_purge.assert_not_called()


class TestArchivedJobSerialization:
    async def test_archived_job_serves_persisted_columns_without_manifest_io(
        self, experiment: Experiment, db_session: AsyncSession, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Archived experiments keep job rows after files are gone; serialize columns, not manifests."""
        gmx = GromacsJob(
            id="job-gmx",
            experiment_id=EXP_ID,
            engine=Engine.GMX,
            simulation_path="x.simulation.json",
            np=1,
            ntomp=1,
            pme=DeviceType.CPU,
            nb=DeviceType.CPU,
        )
        gmx._nsteps = 50000
        gmx._start_timestamp = 111
        gmx._finish_timestamp = 222
        gmx._performance = 12.5
        gmx._last_known_status = JobStatus.FINISHED
        amber = AmberJob(
            id="job-amber",
            experiment_id=EXP_ID,
            engine=Engine.AMBER,
            simulation_path="y.simulation.json",
            np=1,
            ntomp=1,
            binary=AmberBinary.PMEMD_MPI,
            ewald=EwaldPreset.DEFAULT,
        )
        amber._nsteps = 10000
        amber._performance = 40.0
        amber._last_known_status = JobStatus.FINISHED
        db_session.add_all([gmx, amber])
        experiment.archived_at = datetime.now(UTC)
        experiment = await _reload(db_session)
        (tmp_path / EXP_ID).rmdir()

        with _job_active(False), caplog.at_level(logging.WARNING, logger="core.schemas"):
            await experiment.refresh()
            data = ExperimentOut.model_validate(experiment).model_dump(mode="json")

        assert not [r for r in caplog.records if "Failed to compute" in r.message]
        jobs = {job["engine"]: job for job in data["simulation_jobs"]}
        assert jobs["GMX"]["nsteps"] == 50000
        assert jobs["GMX"]["nsteps_done"] == 50000
        assert jobs["GMX"]["performance"] == 12.5
        assert jobs["GMX"]["start_timestamp"] == 111
        assert jobs["GMX"]["finish_timestamp"] == 222
        assert jobs["GMX"]["estimated_time"] is None
        assert jobs["GMX"]["log_lines"] == {}
        assert jobs["AMBER"]["nsteps"] == 10000
        assert jobs["AMBER"]["nsteps_done"] == 10000
        assert jobs["AMBER"]["performance"] == 40.0
        assert jobs["AMBER"]["estimated_time"] is None


class TestArchivedSerialization:
    async def test_snapshot_fields_served(
        self, experiment: Experiment, db_session: AsyncSession, tmp_path: Path
    ) -> None:
        experiment.archived_at = datetime.now(UTC)
        experiment.archived_step = 4
        experiment.archived_status = "published"
        experiment.archived_size_bytes = 9000
        experiment = await _reload(db_session)
        (tmp_path / EXP_ID).rmdir()
        with _job_active(False):
            await experiment.refresh()
        data = ExperimentOut.model_validate(experiment).model_dump(mode="json")

        assert data["archive_state"] == "archived"
        assert data["archived_at"] is not None
        assert data["step"] == 4
        assert data["status"] == "published"
        assert data["size_bytes"] == 9000
        assert "archived_step" not in data
        assert "archived_status" not in data
        assert "archived_size_bytes" not in data


class TestFrozenGates:
    async def test_publish_while_archived_409(self, experiment: Experiment, db_session: AsyncSession) -> None:
        experiment.archived_at = datetime.now(UTC)
        with _job_active(False), pytest.raises(Conflict):
            await experiment.publish(db_session, target="mdposit", simulation_path="x")

    async def test_publish_while_archiving_409(self, experiment: Experiment, db_session: AsyncSession) -> None:
        """A publish racing the archiving window would read files the worker is about to delete."""
        experiment.archived_step = 3
        experiment.archived_status = "ready"
        with _job_active(True), pytest.raises(Conflict):
            await experiment.publish(db_session, target="mdposit", simulation_path="x")

    async def test_notebook_start_while_archived_409(self, experiment: Experiment) -> None:
        experiment.archived_at = datetime.now(UTC)
        with pytest.raises(Conflict):
            await experiment.notebook.start()
