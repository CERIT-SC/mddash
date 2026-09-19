"""Unit tests for experiment archive/restore lifecycle."""

from collections.abc import Generator
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import Mock, patch

import pytest
from archive.status import ArchiveDirection, ArchiveState, ArchiveStatus, write_status
from cache import archive_status_cache
from enums import Engine
from errors import ApiError
from extensions import db
from models import Experiment, Notebook
from pytest_mock import MockerFixture
from schemas import ExperimentSchema
from werkzeug.exceptions import Conflict

EXP_ID = "abcde"


@pytest.fixture
def experiment(app, tmp_path: Path) -> Generator:
    archive_status_cache.clear()
    with patch("models.experiment.DATA_DIR", tmp_path):
        exp = Experiment(id=EXP_ID, name="test", engine=Engine.GMX)  # type: ignore[call-arg]
        db.session.add(exp)
        db.session.add(Notebook(experiment_id=EXP_ID))  # type: ignore[call-arg]
        db.session.commit()
        (tmp_path / EXP_ID).mkdir()
        yield exp
        archive_status_cache.clear()
        db.session.rollback()


@pytest.fixture
def s3():
    with patch("models.experiment.S3_BUCKET", "test-bucket"):
        yield


def _submit_ok(direction: str, experiment_id: str, data_dir: Path) -> str:
    return "attempt-1"


class TestArchiveGates:
    def test_no_s3_config_400(self, experiment: Experiment) -> None:
        from errors import ApiError

        with patch("models.experiment.S3_BUCKET", ""), pytest.raises(ApiError) as exc_info:
            experiment.archive()
        assert exc_info.value.code == 400

    def test_live_simulation_job_409(self, experiment: Experiment, mocker: MockerFixture) -> None:
        from enums import DeviceType
        from models import GromacsJob

        job = GromacsJob(
            id="job-1",
            experiment_id=EXP_ID,
            engine=Engine.GMX,
            simulation_path="x.simulation.json",
            np=1,
            ntomp=1,
            pme=DeviceType.CPU,
            nb=DeviceType.CPU,
        )  # type: ignore[call-arg]
        db.session.add(job)
        db.session.commit()
        mocker.patch("models.simulation_job.mdrun").get_gmx_job.return_value = {"status": "RUNNING"}
        with (
            patch("models.experiment.S3_BUCKET", "test-bucket"),
            pytest.raises(ApiError) as exc_info,
        ):
            experiment.archive()
        assert exc_info.value.problem_type == "urn:mddash:archive-conflict"

    def test_active_upload_409(self, experiment: Experiment) -> None:
        with (
            patch("models.experiment.S3_BUCKET", "test-bucket"),
            patch("models.experiment.read_status", return_value=Mock(state="running")),
            patch("models.experiment.is_upload_active", return_value=True),
            pytest.raises(ApiError) as exc_info,
        ):
            experiment.archive()
        assert exc_info.value.problem_type == "urn:mddash:archive-conflict"

    def test_already_archived_409(self, experiment: Experiment, s3) -> None:
        experiment.archived_at = datetime.now(UTC)
        with patch("archive.submission.is_job_active", return_value=False), pytest.raises(ApiError) as exc_info:
            experiment.archive()
        assert exc_info.value.problem_type == "urn:mddash:archive-conflict"

    def test_running_notebook_is_stopped(self, experiment: Experiment, s3) -> None:
        with (
            patch.object(Notebook, "stop") as mock_stop,
            patch("models.experiment.archive_submission.submit_job", side_effect=_submit_ok),
        ):
            experiment.archive()
        mock_stop.assert_called_once()


class TestArchiveSubmit:
    def test_snapshots_and_submit(self, experiment: Experiment, s3, tmp_path: Path) -> None:
        with (
            patch("models.experiment.DATA_DIR", tmp_path),
            patch("models.experiment.archive_submission.submit_job", side_effect=_submit_ok) as mock_submit,
        ):
            attempt = experiment.archive()
        assert attempt == "attempt-1"
        mock_submit.assert_called_once()
        direction, exp_id, _ = mock_submit.call_args[0]
        assert direction == ArchiveDirection.ARCHIVE.value
        assert exp_id == EXP_ID

        db.session.refresh(experiment)
        assert experiment.archived_step is not None
        assert experiment.archived_status is not None
        assert experiment.archived_at is None  # set by reconciliation after local deletion


class TestRestoreGates:
    def test_not_archived_409(self, experiment: Experiment, s3) -> None:
        with pytest.raises(ApiError) as exc_info:
            experiment.restore()
        assert exc_info.value.problem_type == "urn:mddash:archive-conflict"

    def test_existing_dir_409(self, experiment: Experiment, s3, tmp_path: Path) -> None:
        experiment.archived_at = datetime.now(UTC)
        with (
            patch("models.experiment.DATA_DIR", tmp_path),
            patch("archive.submission.is_job_active", return_value=False),
            pytest.raises(ApiError) as exc_info,
        ):
            experiment.restore()
        assert exc_info.value.problem_type == "urn:mddash:archive-conflict"

    def test_retry_after_failed_restore(self, experiment: Experiment, s3, tmp_path: Path) -> None:
        """A failed restore leaves dir + FAILED doc; that doc is the retry sentinel."""
        experiment.archived_at = datetime.now(UTC)
        write_status(
            ArchiveStatus(attempt_id="a", state=ArchiveState.FAILED.value, direction="restore", reason="check"),
            EXP_ID,
            tmp_path,
        )
        with (
            patch("models.experiment.DATA_DIR", tmp_path),
            patch("archive.submission.is_job_active", return_value=False),
            patch("models.experiment.archive_submission.submit_job", side_effect=_submit_ok) as mock_submit,
        ):
            assert experiment.restore() == "attempt-1"
        mock_submit.assert_called_once()

    def test_stale_running_doc_retryable(self, experiment: Experiment, s3, tmp_path: Path) -> None:
        """An in-flight restore doc with a dead Job is retryable like a FAILED one."""
        experiment.archived_at = datetime.now(UTC)
        write_status(
            ArchiveStatus(attempt_id="a", state=ArchiveState.RUNNING.value, direction="restore"), EXP_ID, tmp_path
        )
        with (
            patch("models.experiment.DATA_DIR", tmp_path),
            patch("archive.submission.is_job_active", return_value=False),
            patch("models.experiment.archive_submission.submit_job", side_effect=_submit_ok) as mock_submit,
        ):
            assert experiment.restore() == "attempt-1"
        mock_submit.assert_called_once()

    def test_happy_path(self, experiment: Experiment, s3, tmp_path: Path) -> None:
        experiment.archived_at = datetime.now(UTC)
        (tmp_path / EXP_ID).rmdir()
        with (
            patch("models.experiment.DATA_DIR", tmp_path),
            patch("archive.submission.is_job_active", return_value=False),
            patch("models.experiment.archive_submission.submit_job", side_effect=_submit_ok) as mock_submit,
        ):
            attempt = experiment.restore()
        assert attempt == "attempt-1"
        assert mock_submit.call_args[0][0] == ArchiveDirection.RESTORE.value


class TestArchiveStateReconciliation:
    def _snap(self, experiment: Experiment) -> None:
        experiment.archived_step = 2
        experiment.archived_status = "running"
        experiment.archived_size_bytes = 1234
        db.session.commit()

    def test_plain_experiment_no_io(self, experiment: Experiment) -> None:
        """No markers -> None without touching disk or K8s."""
        with patch("models.experiment.archive_submission.is_job_active") as mock_active:
            assert experiment.archive_state is None
        mock_active.assert_not_called()

    def test_archiving_while_job_live(self, experiment: Experiment, tmp_path: Path) -> None:
        self._snap(experiment)
        with (
            patch("models.experiment.DATA_DIR", tmp_path),
            patch("archive.submission.is_job_active", return_value=True),
        ):
            assert experiment.archive_state == "archiving"

    def test_archived_after_dir_deleted(self, experiment: Experiment, tmp_path: Path) -> None:
        self._snap(experiment)
        (tmp_path / EXP_ID).rmdir()
        with (
            patch("models.experiment.DATA_DIR", tmp_path),
            patch("archive.submission.is_job_active", return_value=False),
        ):
            assert experiment.archive_state == "archived"
        db.session.refresh(experiment)
        assert experiment.archived_at is not None

    def test_archive_failed_from_doc(self, experiment: Experiment, tmp_path: Path) -> None:
        self._snap(experiment)
        write_status(
            ArchiveStatus(attempt_id="a", state=ArchiveState.FAILED.value, direction="archive", reason="check"),
            EXP_ID,
            tmp_path,
        )
        with (
            patch("models.experiment.DATA_DIR", tmp_path),
            patch("archive.submission.is_job_active", return_value=False),
        ):
            assert experiment.archive_state == "archive_failed"

    def test_archive_failed_job_missing(self, experiment: Experiment, tmp_path: Path) -> None:
        self._snap(experiment)
        with (
            patch("models.experiment.DATA_DIR", tmp_path),
            patch("archive.submission.is_job_active", return_value=False),
        ):
            assert experiment.archive_state == "archive_failed"

    def test_dead_job_with_running_doc_is_failed(self, experiment: Experiment, tmp_path: Path) -> None:
        """Job evicted after writing running (backoffLimit 0): must not freeze at archiving."""
        self._snap(experiment)
        write_status(
            ArchiveStatus(attempt_id="a", state=ArchiveState.RUNNING.value, direction="archive"), EXP_ID, tmp_path
        )
        with (
            patch("models.experiment.DATA_DIR", tmp_path),
            patch("archive.submission.is_job_active", return_value=False),
        ):
            assert experiment.archive_state == "archive_failed"

    def test_job_liveness_cached_across_reads(self, experiment: Experiment, tmp_path: Path) -> None:
        """List serialization must not fan out K8s reads per experiment per request."""
        self._snap(experiment)
        with (
            patch("models.experiment.DATA_DIR", tmp_path),
            patch("archive.submission.is_job_active", return_value=False) as mock_active,
        ):
            assert experiment.archive_state == "archive_failed"
            assert experiment.archive_state == "archive_failed"
        assert mock_active.call_count == 1

    def test_archived_baseline(self, experiment: Experiment, tmp_path: Path) -> None:
        experiment.archived_at = datetime.now(UTC)
        (tmp_path / EXP_ID).rmdir()
        with (
            patch("models.experiment.DATA_DIR", tmp_path),
            patch("archive.submission.is_job_active", return_value=False),
        ):
            assert experiment.archive_state == "archived"

    def test_restoring(self, experiment: Experiment, tmp_path: Path) -> None:
        experiment.archived_at = datetime.now(UTC)
        write_status(
            ArchiveStatus(attempt_id="a", state=ArchiveState.RUNNING.value, direction="restore"), EXP_ID, tmp_path
        )
        with (
            patch("models.experiment.DATA_DIR", tmp_path),
            patch("archive.submission.is_job_active", return_value=True),
        ):
            assert experiment.archive_state == "restoring"

    def test_restore_completion_clears_flags(self, experiment: Experiment, tmp_path: Path) -> None:
        experiment.archived_at = datetime.now(UTC)
        experiment.archived_step = 2
        experiment.archived_status = "running"
        experiment.archived_size_bytes = 1234
        db.session.commit()
        write_status(
            ArchiveStatus(attempt_id="a", state=ArchiveState.COMPLETED.value, direction="restore"), EXP_ID, tmp_path
        )
        with (
            patch("models.experiment.DATA_DIR", tmp_path),
            patch("archive.submission.is_job_active", return_value=False),
        ):
            assert experiment.archive_state is None
        db.session.refresh(experiment)
        assert experiment.archived_at is None
        assert experiment.archived_step is None
        assert experiment.archived_size_bytes is None

    def test_restore_failed(self, experiment: Experiment, tmp_path: Path) -> None:
        experiment.archived_at = datetime.now(UTC)
        write_status(
            ArchiveStatus(attempt_id="a", state=ArchiveState.FAILED.value, direction="restore", reason="copy"),
            EXP_ID,
            tmp_path,
        )
        with (
            patch("models.experiment.DATA_DIR", tmp_path),
            patch("archive.submission.is_job_active", return_value=False),
        ):
            assert experiment.archive_state == "restore_failed"

    def test_live_job_outranks_failed_sentinel(self, experiment: Experiment, tmp_path: Path) -> None:
        """A retried restore reads as restoring once its Job exists, not when the worker rewrites the doc."""
        experiment.archived_at = datetime.now(UTC)
        write_status(
            ArchiveStatus(attempt_id="a", state=ArchiveState.FAILED.value, direction="restore", reason="copy"),
            EXP_ID,
            tmp_path,
        )
        with (
            patch("models.experiment.DATA_DIR", tmp_path),
            patch("archive.submission.is_job_active", return_value=True),
        ):
            assert experiment.archive_state == "restoring"

    def test_stale_running_restore_doc_is_failed(self, experiment: Experiment, tmp_path: Path) -> None:
        """An in-flight restore doc with no live Job (evicted, backoffLimit 0) is failed, as in the archive direction."""
        experiment.archived_at = datetime.now(UTC)
        write_status(
            ArchiveStatus(attempt_id="a", state=ArchiveState.RUNNING.value, direction="restore"), EXP_ID, tmp_path
        )
        with (
            patch("models.experiment.DATA_DIR", tmp_path),
            patch("archive.submission.is_job_active", return_value=False),
        ):
            assert experiment.archive_state == "restore_failed"

    def test_archive_state_consumed_from_pre_dump_stash(self, experiment: Experiment, tmp_path: Path) -> None:
        """The property serves the pre_dump reconciliation, so no mid-dump flip can split archived_at from archive_state."""
        self._snap(experiment)
        calls = 0

        def flip_after_first(_self: Experiment) -> str:
            nonlocal calls
            calls += 1
            if calls > 1:  # any mid-dump re-check flips the world
                _self.archived_at = datetime.now(UTC)
                return "archived"
            return "archiving"

        with (
            patch("models.experiment.DATA_DIR", tmp_path),
            patch.object(Experiment, "_read_archive_state", flip_after_first),
        ):
            data = ExperimentSchema().dump(experiment)

        assert calls == 1  # the property did not re-reconcile
        assert data["archive_state"] == "archiving"
        assert data["archived_at"] is None  # consistent pair from one reconciliation

    def test_direct_access_reconciles_fresh(self, experiment: Experiment, tmp_path: Path) -> None:
        """Without a dump, the property reconciles on every access (no stash)."""
        experiment.archived_at = datetime.now(UTC)
        (tmp_path / EXP_ID).rmdir()
        with (
            patch("models.experiment.DATA_DIR", tmp_path),
            patch("archive.submission.is_job_active", return_value=False),
            patch.object(Experiment, "_read_archive_state", return_value="archived") as mock_read,
        ):
            assert experiment.archive_state == "archived"
            assert experiment.archive_state == "archived"
        assert mock_read.call_count == 2


class TestSubmissionFailure:
    def test_archive_submit_failure_409_problem(self, experiment: Experiment, s3, tmp_path: Path) -> None:
        from archive.submission import SubmissionError
        from errors import ApiError

        with (
            patch("models.experiment.DATA_DIR", tmp_path),
            patch(
                "models.experiment.archive_submission.submit_job",
                side_effect=SubmissionError("object is being deleted"),
            ),
            pytest.raises(ApiError) as exc_info,
        ):
            experiment.archive()
        assert exc_info.value.code == 409
        assert exc_info.value.problem_type == "urn:mddash:archive-submission-failed"

    def test_restore_submit_failure_409_problem(self, experiment: Experiment, s3, tmp_path: Path) -> None:
        from archive.submission import SubmissionError
        from errors import ApiError

        experiment.archived_at = datetime.now(UTC)
        (tmp_path / EXP_ID).rmdir()
        with (
            patch("models.experiment.DATA_DIR", tmp_path),
            patch("archive.submission.is_job_active", return_value=False),
            patch(
                "models.experiment.archive_submission.submit_job",
                side_effect=SubmissionError("object is being deleted"),
            ),
            pytest.raises(ApiError) as exc_info,
        ):
            experiment.restore()
        assert exc_info.value.code == 409
        assert exc_info.value.problem_type == "urn:mddash:archive-submission-failed"


class TestDeleteWithArchive:
    def test_archived_delete_purges(self, experiment: Experiment, tmp_path: Path) -> None:
        experiment.archived_at = datetime.now(UTC)
        (tmp_path / EXP_ID).rmdir()
        with (
            patch("models.experiment.archive_submission.delete_jobs") as mock_delete,
            patch("models.experiment.archive_submission.submit_purge_job") as mock_purge,
            patch.object(Notebook, "stop"),
        ):
            experiment.delete()
        mock_delete.assert_called_once_with(EXP_ID)
        mock_purge.assert_called_once_with(EXP_ID)

    def test_active_delete_no_purge(self, experiment: Experiment) -> None:
        with (
            patch("models.experiment.archive_submission.delete_jobs"),
            patch("models.experiment.archive_submission.submit_purge_job") as mock_purge,
            patch.object(Notebook, "stop"),
        ):
            experiment.delete()
        mock_purge.assert_not_called()


class TestArchivedJobSerialization:
    def test_archived_job_serves_persisted_columns_without_manifest_io(
        self, experiment: Experiment, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Archived experiments keep job rows after files are gone; serialize columns, not manifests."""
        import logging

        from enums import AmberBinary, DeviceType, EwaldPreset, JobStatus
        from models import AmberJob, GromacsJob

        gmx = GromacsJob(
            id="job-gmx",
            experiment_id=EXP_ID,
            engine=Engine.GMX,
            simulation_path="x.simulation.json",
            np=1,
            ntomp=1,
            pme=DeviceType.CPU,
            nb=DeviceType.CPU,
        )  # type: ignore[call-arg]
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
        )  # type: ignore[call-arg]
        amber._nsteps = 10000
        amber._performance = 40.0
        amber._last_known_status = JobStatus.FINISHED
        db.session.add_all([gmx, amber])
        experiment.archived_at = datetime.now(UTC)
        db.session.commit()
        (tmp_path / EXP_ID).rmdir()

        with (
            patch("models.experiment.DATA_DIR", tmp_path),
            patch("archive.submission.is_job_active", return_value=False),
            caplog.at_level(logging.WARNING, logger="schemas.base"),
        ):
            data = ExperimentSchema().dump(experiment)

        assert not [r for r in caplog.records if "Failed to compute property" in r.message]
        jobs = {job["engine"]: job for job in data["simulation_jobs"]}
        assert jobs["GMX"]["nsteps"] == 50000
        assert jobs["GMX"]["nsteps_done"] == 50000
        assert jobs["GMX"]["performance"] == 12.5
        assert jobs["GMX"]["start_timestamp"] == 111
        assert jobs["GMX"]["finish_timestamp"] == 222
        assert jobs["GMX"]["estimated_time"] is None
        assert jobs["GMX"]["init_step"] == 0
        assert jobs["GMX"]["log_lines"] == {}
        assert jobs["AMBER"]["nsteps"] == 10000
        assert jobs["AMBER"]["nsteps_done"] == 10000
        assert jobs["AMBER"]["performance"] == 40.0
        assert jobs["AMBER"]["estimated_time"] is None


class TestArchivedSerialization:
    def test_snapshot_fields_served(self, experiment: Experiment, tmp_path: Path) -> None:
        experiment.archived_at = datetime.now(UTC)
        experiment.archived_step = 4
        experiment.archived_status = "published"
        experiment.archived_size_bytes = 9000
        db.session.commit()
        (tmp_path / EXP_ID).rmdir()
        with (
            patch("models.experiment.DATA_DIR", tmp_path),
            patch("archive.submission.is_job_active", return_value=False),
        ):
            data = ExperimentSchema().dump(experiment)

        assert data["archive_state"] == "archived"
        assert data["archived_at"] is not None
        assert data["step"] == 4
        assert data["status"] == "published"
        assert data["size_bytes"] == 9000
        assert "archived_step" not in data
        assert "archived_status" not in data
        assert "archived_size_bytes" not in data


class TestFrozenGates:
    def test_publish_while_archived_409(self, experiment: Experiment) -> None:
        experiment.archived_at = datetime.now(UTC)
        with pytest.raises(Conflict):
            experiment.publish(target="mdposit", simulation_path="x")

    def test_publish_while_archiving_409(self, experiment: Experiment, tmp_path: Path) -> None:
        """A publish racing the archiving window would read files the worker is about to delete."""
        experiment.archived_step = 3
        experiment.archived_status = "ready"
        db.session.commit()
        with (
            patch("models.experiment.DATA_DIR", tmp_path),
            patch("archive.submission.is_job_active", return_value=True),
            pytest.raises(Conflict),
        ):
            experiment.publish(target="mdposit", simulation_path="x")

    def test_notebook_start_while_archived_409(self, experiment: Experiment) -> None:
        experiment.archived_at = datetime.now(UTC)
        with pytest.raises(Conflict):
            experiment.notebook.start()
