"""Unit tests for the run lifecycle: non-destructive stop, GMX extension, segment history."""

import json
import re
from datetime import UTC, datetime, timedelta
from http import HTTPStatus
from pathlib import Path
from uuid import uuid4

import pytest
from enums import AmberBinary, DeviceType, Engine, EwaldPreset, JobStatus
from extensions import db
from flask import Flask
from flask.testing import FlaskClient
from manifest_schema import schema_url
from models import Experiment
from models.amber_job import AmberJob
from models.gromacs_job import GromacsJob
from models.simulation import Simulation
from pytest_mock import MockerFixture

GMX_FILES = {
    "run_input": "production/protein.tpr",
    "reference_structure": "analysis/protein-reference.gro",
    "trajectory": "production/protein.xtc",
}

AMBER_FILES = {
    "topology": "prod.prmtop",
    "coordinates": "prod.inpcrd",
    "control": "prod.mdin",
    "reference_structure": "reference.pdb",
    "trajectory": "prod.nc",
}


@pytest.fixture(autouse=True)
def _model_data_dirs(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Job models bind config.DATA_DIR at import; rebind it to the test data dir (like test_simulation.py does)."""
    monkeypatch.setattr("models.gromacs_job.DATA_DIR", tmp_path)
    monkeypatch.setattr("models.amber_job.DATA_DIR", tmp_path)


@pytest.fixture
def experiment_id(app: Flask) -> str:
    """Seed a minimal experiment; DATA_DIR is patched to tmp_path by conftest."""
    with app.app_context():
        exp = Experiment(id="lifec", name="Lifecycle", notebooks_repo="https://github.com/t/r.git")
        db.session.add(exp)
        db.session.commit()
        return exp.id


def _write_gmx_simulation(exp_dir: Path, extra_args: str = "", name: str = "protein") -> str:
    """Write a valid GMX manifest plus its input files."""
    exp_dir.mkdir(parents=True, exist_ok=True)
    simulation_path = "protein.simulation.json"
    content = {
        "$schema": schema_url(Engine.GMX),
        "name": name,
        "engine": "GMX",
        "files": GMX_FILES,
        "extra_args": extra_args,
    }
    (exp_dir / simulation_path).write_text(json.dumps(content))
    for role in ("run_input", "reference_structure"):
        f = exp_dir / GMX_FILES[role]
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(f"demo {role}\n")
    return simulation_path


def _write_amber_simulation(exp_dir: Path) -> str:
    exp_dir.mkdir(parents=True, exist_ok=True)
    simulation_path = "prod.simulation.json"
    content = {
        "$schema": schema_url(Engine.AMBER),
        "name": "prod",
        "engine": "AMBER",
        "files": AMBER_FILES,
        "extra_args": "",
    }
    (exp_dir / simulation_path).write_text(json.dumps(content))
    for role in ("topology", "coordinates", "control", "reference_structure"):
        (exp_dir / AMBER_FILES[role]).write_text(f"demo {role}\n")
    return simulation_path


def _add_gmx_job(
    app: Flask,
    exp_id: str,
    simulation_path: str,
    job_id: str,
    status: JobStatus | None = JobStatus.FINISHED,
    created_at: datetime | None = None,
    **kwargs: object,
) -> GromacsJob:
    """Persist a GromacsJob row without going through MDRun."""
    with app.app_context():
        job = GromacsJob(
            id=job_id,
            experiment_id=exp_id,
            simulation_path=simulation_path,
            np=8,
            ntomp=1,
            pme=DeviceType.CPU,
            nb=DeviceType.GPU,
            _last_known_status=status,
            created_at=created_at or datetime.now(UTC),
            **kwargs,
        )
        db.session.add(job)
        db.session.commit()
        found = db.session.get(GromacsJob, job_id)
        assert found is not None
        return found


def _add_amber_job(app: Flask, exp_id: str, simulation_path: str, job_id: str, status: JobStatus | None) -> AmberJob:
    with app.app_context():
        job = AmberJob(
            id=job_id,
            experiment_id=exp_id,
            simulation_path=simulation_path,
            np=1,
            ntomp=8,
            binary=AmberBinary.PMEMD_CUDA,
            ewald=EwaldPreset.DEFAULT,
            _last_known_status=status,
        )
        db.session.add(job)
        db.session.commit()
        found = db.session.get(AmberJob, job_id)
        assert found is not None
        return found


def _mock_mdrun(mocker: MockerFixture, status: str = "finished") -> dict:
    """Patch all mdrun client entry points the job models call."""
    return {
        "get_gmx": mocker.patch("clients.mdrun.get_gmx_job", return_value={"id": "x", "status": status}),
        "get_amber": mocker.patch("clients.mdrun.get_amber_job", return_value={"id": "x", "status": status}),
        "create": mocker.patch(
            "clients.mdrun.create_job",
            side_effect=lambda **_: {"id": str(uuid4()), "status": "running"},
        ),
        "delete_gmx": mocker.patch("clients.mdrun.delete_gmx_job"),
        "delete_amber": mocker.patch("clients.mdrun.delete_amber_job"),
        "stop": mocker.patch("clients.mdrun.stop_job"),
    }


_ONE_HOUR_AGO = datetime.now(UTC) - timedelta(hours=1)


def _stop_mocks(mocker: MockerFixture, engine: str = "gmx") -> dict:
    """MDRun mocks where a successful stop reports "stopped" on subsequent reads."""
    get_key = "get_gmx" if engine == "gmx" else "get_amber"

    def get_status(_job_id: str) -> dict:
        return {"id": _job_id, "status": "stopped" if mdrun["stop"].called else "running"}

    mdrun = _mock_mdrun(mocker, status="running")
    mdrun[get_key].side_effect = get_status
    return mdrun


class TestStop:
    """Stopping preserves data, files, and job history."""

    def test_stop_live_gmx_job(
        self, client: FlaskClient, app: Flask, experiment_id: str, tmp_path: Path, mocker: MockerFixture
    ) -> None:
        mdrun = _stop_mocks(mocker)
        sim_path = _write_gmx_simulation(tmp_path / experiment_id)
        job = _add_gmx_job(app, experiment_id, sim_path, "job-live", JobStatus.RUNNING)
        log = tmp_path / experiment_id / "production/protein.log"
        log.write_text("growing log\n")

        response = client.post(f"/dash/api/experiments/{experiment_id}/gmx/{sim_path}/stop")

        assert response.status_code == HTTPStatus.NO_CONTENT
        mdrun["stop"].assert_called_once_with(job.id, "gmx")
        with app.app_context():
            stopped = db.session.get(GromacsJob, job.id)
            assert stopped is not None, "row must be kept"
            assert stopped._last_known_status is JobStatus.STOPPED
        assert log.exists(), "result files must survive a stop"

    def test_stop_keeps_finished_when_the_run_beats_the_stop(
        self, client: FlaskClient, app: Flask, experiment_id: str, tmp_path: Path, mocker: MockerFixture
    ) -> None:
        """A job that finishes between the guard and the stop must stay FINISHED, not STOPPED."""
        mdrun = _stop_mocks(mocker)

        def finished_outcome(_job_id: str) -> dict:
            return {"id": _job_id, "status": "finished" if mdrun["stop"].called else "running"}

        mdrun["get_gmx"].side_effect = finished_outcome
        sim_path = _write_gmx_simulation(tmp_path / experiment_id)
        job = _add_gmx_job(app, experiment_id, sim_path, "job-fast", JobStatus.RUNNING)

        response = client.post(f"/dash/api/experiments/{experiment_id}/gmx/{sim_path}/stop")

        assert response.status_code == HTTPStatus.NO_CONTENT
        with app.app_context():
            row = db.session.get(GromacsJob, job.id)
            assert row is not None
            assert row._last_known_status is JobStatus.FINISHED

    def test_stop_terminal_gmx_job_is_400(
        self, client: FlaskClient, app: Flask, experiment_id: str, tmp_path: Path, mocker: MockerFixture
    ) -> None:
        _mock_mdrun(mocker)
        sim_path = _write_gmx_simulation(tmp_path / experiment_id)
        _add_gmx_job(app, experiment_id, sim_path, "job-done", JobStatus.FINISHED)

        response = client.post(f"/dash/api/experiments/{experiment_id}/gmx/{sim_path}/stop")

        assert response.status_code == HTTPStatus.BAD_REQUEST

    def test_stop_gmx_missing_job_is_404(self, client: FlaskClient, experiment_id: str) -> None:
        response = client.post(f"/dash/api/experiments/{experiment_id}/gmx/nope.simulation.json/stop")

        assert response.status_code == HTTPStatus.NOT_FOUND

    def test_stop_live_amber_job(
        self, client: FlaskClient, app: Flask, experiment_id: str, tmp_path: Path, mocker: MockerFixture
    ) -> None:
        mdrun = _stop_mocks(mocker, engine="amber")
        sim_path = _write_amber_simulation(tmp_path / experiment_id)
        job = _add_amber_job(app, experiment_id, sim_path, "amber-live", JobStatus.RUNNING)

        response = client.post(f"/dash/api/experiments/{experiment_id}/amber/{sim_path}/stop")

        assert response.status_code == HTTPStatus.NO_CONTENT
        mdrun["stop"].assert_called_once_with(job.id, "amber")
        with app.app_context():
            stopped = db.session.get(AmberJob, job.id)
            assert stopped is not None
            assert stopped._last_known_status is JobStatus.STOPPED


class TestExtend:
    """GMX extension resumes from the checkpoint with cumulative -nsteps."""

    def _setup_finished_segment(
        self, app: Flask, exp_id: str, tmp_path: Path, extra_args: str = "", **job_kwargs: object
    ) -> str:
        sim_path = _write_gmx_simulation(tmp_path / exp_id, extra_args=extra_args)
        _add_gmx_job(app, exp_id, sim_path, "seg-1", JobStatus.FINISHED, created_at=_ONE_HOUR_AGO, **job_kwargs)
        return sim_path

    def _write_checkpoint(self, exp_dir: Path) -> None:
        (exp_dir / "production/protein.cpt").write_bytes(b"cpt\n")

    def test_extend_creates_segment_with_composed_args(
        self, client: FlaskClient, app: Flask, experiment_id: str, tmp_path: Path, mocker: MockerFixture
    ) -> None:
        mdrun = _mock_mdrun(mocker)
        sim_path = self._setup_finished_segment(app, experiment_id, tmp_path, _nsteps=100000, _performance=68.5)
        self._write_checkpoint(tmp_path / experiment_id)

        response = client.post(f"/dash/api/experiments/{experiment_id}/gmx/{sim_path}/extend", json={"nsteps": 50000})

        assert response.status_code == HTTPStatus.CREATED
        kwargs = mdrun["create"].call_args.kwargs
        assert kwargs["tpr_name"] == "production/protein.tpr"
        assert kwargs["extra_args"] == "-cpi protein.cpt -nsteps 150000"
        # Hardware inherited from the previous segment.
        assert (kwargs["pme"], kwargs["nb"], kwargs["np"], kwargs["ntomp"]) == ("cpu", "gpu", 8, 1)
        # Manifest itself stays untouched.
        manifest = json.loads((tmp_path / experiment_id / sim_path).read_text())
        assert manifest["extra_args"] == ""

        with app.app_context():
            jobs = GromacsJob.query.filter_by(experiment_id=experiment_id, simulation_path=sim_path).all()
            assert len(jobs) == 2, "extension keeps segment history"
            new_segment = next(j for j in jobs if j.id != "seg-1")
            assert new_segment._nsteps == 150000

    def test_extend_respects_manifest_nsteps_override(
        self, client: FlaskClient, app: Flask, experiment_id: str, tmp_path: Path, mocker: MockerFixture
    ) -> None:
        mdrun = _mock_mdrun(mocker)
        sim_path = self._setup_finished_segment(app, experiment_id, tmp_path, extra_args="-nsteps 80000")
        self._write_checkpoint(tmp_path / experiment_id)

        response = client.post(f"/dash/api/experiments/{experiment_id}/gmx/{sim_path}/extend", json={"nsteps": 50000})

        assert response.status_code == HTTPStatus.CREATED
        kwargs = mdrun["create"].call_args.kwargs
        # The stale override is stripped and replaced with the cumulative total.
        assert kwargs["extra_args"] == "-cpi protein.cpt -nsteps 130000"

    def test_extend_chains_cumulative_totals(
        self, client: FlaskClient, app: Flask, experiment_id: str, tmp_path: Path, mocker: MockerFixture
    ) -> None:
        mdrun = _mock_mdrun(mocker)
        sim_path = self._setup_finished_segment(app, experiment_id, tmp_path, _nsteps=100000, _performance=68.5)
        self._write_checkpoint(tmp_path / experiment_id)

        client.post(f"/dash/api/experiments/{experiment_id}/gmx/{sim_path}/extend", json={"nsteps": 50000})
        # The new segment finishes (its MDRun entry reports finished), then extends again.
        with app.app_context():
            seg2 = (
                GromacsJob.query
                .filter_by(experiment_id=experiment_id, simulation_path=sim_path)
                .order_by(GromacsJob.created_at.desc())
                .first()
            )
            seg2._last_known_status = JobStatus.FINISHED
            db.session.commit()

        response = client.post(f"/dash/api/experiments/{experiment_id}/gmx/{sim_path}/extend", json={"nsteps": 25000})

        assert response.status_code == HTTPStatus.CREATED
        kwargs = mdrun["create"].call_args.kwargs
        assert kwargs["extra_args"] == "-cpi protein.cpt -nsteps 175000"

    def test_extend_chains_persisted_total_over_stale_manifest_override(
        self, client: FlaskClient, app: Flask, experiment_id: str, tmp_path: Path, mocker: MockerFixture
    ) -> None:
        """A second extension must build on the persisted cumulative target, never the manifest's stale -nsteps."""
        mdrun = _mock_mdrun(mocker)
        sim_path = self._setup_finished_segment(app, experiment_id, tmp_path, extra_args="-nsteps 80000")
        self._write_checkpoint(tmp_path / experiment_id)

        first = client.post(f"/dash/api/experiments/{experiment_id}/gmx/{sim_path}/extend", json={"nsteps": 50000})
        assert first.status_code == HTTPStatus.CREATED

        # The extension segment finishes, then a second extension follows.
        with app.app_context():
            seg2 = (
                GromacsJob.query
                .filter_by(experiment_id=experiment_id, simulation_path=sim_path)
                .order_by(GromacsJob.created_at.desc())
                .first()
            )
            seg2._last_known_status = JobStatus.FINISHED
            db.session.commit()

        second = client.post(f"/dash/api/experiments/{experiment_id}/gmx/{sim_path}/extend", json={"nsteps": 25000})

        assert second.status_code == HTTPStatus.CREATED
        kwargs = mdrun["create"].call_args.kwargs
        # 130000 (first extension's persisted total) + 25000 — NOT 80000 + 25000,
        # which is what the old override-first precedence would have produced.
        assert kwargs["extra_args"] == "-cpi protein.cpt -nsteps 155000"

    def test_extend_anchors_on_actual_progress_and_freezes_display(
        self, client: FlaskClient, app: Flask, experiment_id: str, tmp_path: Path, mocker: MockerFixture
    ) -> None:
        """A segment stopped short of its target extends from where it stood, not from the target."""
        mdrun = _mock_mdrun(mocker)
        sim_path = self._setup_finished_segment(app, experiment_id, tmp_path, _nsteps=150000)
        # Stopped at 120k out of the 150k target — the log tail holds the truth.
        with app.app_context():
            seg = db.session.get(GromacsJob, "seg-1")
            assert seg is not None
            seg._last_known_status = JobStatus.STOPPED
            seg._nsteps_done = None
            db.session.commit()
        (tmp_path / experiment_id / "production/protein.log").write_text(
            "header\n        120000    2400000.0000     1000.0000\n"
        )
        self._write_checkpoint(tmp_path / experiment_id)

        response = client.post(f"/dash/api/experiments/{experiment_id}/gmx/{sim_path}/extend", json={"nsteps": 20000})

        assert response.status_code == HTTPStatus.CREATED
        kwargs = mdrun["create"].call_args.kwargs
        # 120000 done + 20000 requested — NOT 150000 (target) + 20000.
        assert kwargs["extra_args"] == "-cpi protein.cpt -nsteps 140000"
        with app.app_context():
            old = db.session.get(GromacsJob, "seg-1")
            assert old is not None
            # The frozen value pins the history row: it must keep showing 120,000.
            assert old._nsteps_done == 120000
            assert old.nsteps_done == 120000
            new_segment = (
                GromacsJob.query
                .filter_by(experiment_id=experiment_id, simulation_path=sim_path)
                .order_by(GromacsJob.created_at.desc())
                .first()
            )
            assert new_segment._nsteps == 140000

    def test_extend_anchors_on_step_rows_despite_stop_performance_block(
        self, client: FlaskClient, app: Flask, experiment_id: str, tmp_path: Path, mocker: MockerFixture
    ) -> None:
        """A real TERM-stopped run prints Performance: too — it must neither shortcut the row nor be cached."""
        mdrun = _mock_mdrun(mocker)
        sim_path = self._setup_finished_segment(app, experiment_id, tmp_path, _nsteps=150000)
        with app.app_context():
            seg = db.session.get(GromacsJob, "seg-1")
            assert seg is not None
            seg._last_known_status = JobStatus.STOPPED
            db.session.commit()
        # Real TERM-stop trailer: step rows up to 120k, then a Performance: line.
        (tmp_path / experiment_id / "production/protein.log").write_text(
            "header\n        120000    2400000.0000     1000.0000\nPerformance:        61.2\n"
        )
        self._write_checkpoint(tmp_path / experiment_id)

        response = client.post(f"/dash/api/experiments/{experiment_id}/gmx/{sim_path}/extend", json={"nsteps": 20000})

        assert response.status_code == HTTPStatus.CREATED
        assert mdrun["create"].call_args.kwargs["extra_args"] == "-cpi protein.cpt -nsteps 140000"
        with app.app_context():
            old = db.session.get(GromacsJob, "seg-1")
            assert old is not None
            # Stopped: not a proven 150k completion, and no inherited performance either.
            assert old.nsteps_done == 120000
            assert old.performance is None
            assert old._performance is None

    def test_extend_falls_back_to_target_when_progress_unparseable(
        self, client: FlaskClient, app: Flask, experiment_id: str, tmp_path: Path, mocker: MockerFixture
    ) -> None:
        """With no parseable step rows (e.g. missing log), the anchor falls back to the target."""
        mdrun = _mock_mdrun(mocker)
        sim_path = self._setup_finished_segment(app, experiment_id, tmp_path, _nsteps=150000)
        with app.app_context():
            seg = db.session.get(GromacsJob, "seg-1")
            assert seg is not None
            seg._last_known_status = JobStatus.STOPPED
            db.session.commit()
        self._write_checkpoint(tmp_path / experiment_id)

        response = client.post(f"/dash/api/experiments/{experiment_id}/gmx/{sim_path}/extend", json={"nsteps": 20000})

        assert response.status_code == HTTPStatus.CREATED
        assert mdrun["create"].call_args.kwargs["extra_args"] == "-cpi protein.cpt -nsteps 170000"

    def test_extend_race_loser_gets_400_and_its_mdrun_job_is_deleted(
        self, client: FlaskClient, app: Flask, experiment_id: str, tmp_path: Path, mocker: MockerFixture
    ) -> None:
        """A concurrent extension winning between the live check and our insert is rejected atomically."""
        mdrun = _mock_mdrun(mocker)
        sim_path = self._setup_finished_segment(app, experiment_id, tmp_path, _nsteps=100000, _performance=68.5)
        self._write_checkpoint(tmp_path / experiment_id)

        def concurrent_winner(**kwargs: object) -> dict:
            # A rival request commits its segment after our is_live check but
            # before our insert — exactly the window the unique index closes.
            rival = GromacsJob(
                id="rival-segment",
                experiment_id=experiment_id,
                simulation_path=sim_path,
                np=8,
                ntomp=1,
                pme=DeviceType.CPU,
                nb=DeviceType.GPU,
                engine=Engine.GMX,
                _last_known_status=JobStatus.PENDING,
            )
            db.session.add(rival)
            db.session.commit()
            return {"id": "losing-segment", "status": "running"}

        mdrun["create"].side_effect = concurrent_winner

        response = client.post(f"/dash/api/experiments/{experiment_id}/gmx/{sim_path}/extend", json={"nsteps": 50000})

        assert response.status_code == HTTPStatus.BAD_REQUEST
        assert "already in progress" in response.get_json()["detail"]
        # The orphaned cluster job behind the losing insert is torn down.
        mdrun["delete_gmx"].assert_called_once_with("losing-segment")
        with app.app_context():
            ids = {
                j.id for j in GromacsJob.query.filter_by(experiment_id=experiment_id, simulation_path=sim_path).all()
            }
            assert ids == {"seg-1", "rival-segment"}, "the losing segment must be rolled back"

    def test_extend_rejects_manifest_with_cpi(
        self, client: FlaskClient, app: Flask, experiment_id: str, tmp_path: Path, mocker: MockerFixture
    ) -> None:
        mdrun = _mock_mdrun(mocker)
        sim_path = self._setup_finished_segment(app, experiment_id, tmp_path, extra_args="-cpi state.cpt")
        self._write_checkpoint(tmp_path / experiment_id)

        response = client.post(f"/dash/api/experiments/{experiment_id}/gmx/{sim_path}/extend", json={"nsteps": 50000})

        assert response.status_code == HTTPStatus.BAD_REQUEST
        mdrun["create"].assert_not_called()

    def test_extend_requires_checkpoint(
        self, client: FlaskClient, app: Flask, experiment_id: str, tmp_path: Path, mocker: MockerFixture
    ) -> None:
        mdrun = _mock_mdrun(mocker)
        sim_path = self._setup_finished_segment(app, experiment_id, tmp_path, _nsteps=100000)

        response = client.post(f"/dash/api/experiments/{experiment_id}/gmx/{sim_path}/extend", json={"nsteps": 50000})

        assert response.status_code == HTTPStatus.BAD_REQUEST
        assert "checkpoint" in response.get_json()["detail"].lower()
        mdrun["create"].assert_not_called()

    def test_extend_rejects_live_segment(
        self, client: FlaskClient, app: Flask, experiment_id: str, tmp_path: Path, mocker: MockerFixture
    ) -> None:
        mdrun = _mock_mdrun(mocker, status="running")
        sim_path = _write_gmx_simulation(tmp_path / experiment_id)
        _add_gmx_job(app, experiment_id, sim_path, "seg-live", JobStatus.RUNNING)
        self._write_checkpoint(tmp_path / experiment_id)

        response = client.post(f"/dash/api/experiments/{experiment_id}/gmx/{sim_path}/extend", json={"nsteps": 50000})

        assert response.status_code == HTTPStatus.BAD_REQUEST
        mdrun["create"].assert_not_called()

    def test_extend_requires_existing_run(
        self, client: FlaskClient, app: Flask, experiment_id: str, tmp_path: Path, mocker: MockerFixture
    ) -> None:
        _mock_mdrun(mocker)
        sim_path = _write_gmx_simulation(tmp_path / experiment_id)
        self._write_checkpoint(tmp_path / experiment_id)

        response = client.post(f"/dash/api/experiments/{experiment_id}/gmx/{sim_path}/extend", json={"nsteps": 50000})

        assert response.status_code == HTTPStatus.BAD_REQUEST

    @pytest.mark.parametrize("nsteps", ["abc", 0, -5, None])
    def test_extend_rejects_invalid_nsteps(
        self, client: FlaskClient, app: Flask, experiment_id: str, tmp_path: Path, mocker: MockerFixture, nsteps: object
    ) -> None:
        _mock_mdrun(mocker)
        sim_path = self._setup_finished_segment(app, experiment_id, tmp_path, _nsteps=100000)
        self._write_checkpoint(tmp_path / experiment_id)

        response = client.post(f"/dash/api/experiments/{experiment_id}/gmx/{sim_path}/extend", json={"nsteps": nsteps})

        assert response.status_code == HTTPStatus.BAD_REQUEST


class TestLiveSegmentIndex:
    """DB-level guarantee: one segment with a committed live status per simulation."""

    @pytest.mark.parametrize("winner_status", [JobStatus.PENDING, JobStatus.RUNNING, JobStatus.UNKNOWN])
    def test_second_live_segment_is_rejected(
        self, app: Flask, experiment_id: str, winner_status: JobStatus | None
    ) -> None:
        from sqlalchemy.exc import IntegrityError

        _add_gmx_job(app, experiment_id, "protein.simulation.json", "winner", winner_status)
        with pytest.raises(IntegrityError):
            _add_gmx_job(app, experiment_id, "protein.simulation.json", "rival", JobStatus.PENDING)

    def test_second_segment_after_finish_is_allowed(self, app: Flask, experiment_id: str) -> None:
        _add_gmx_job(app, experiment_id, "protein.simulation.json", "winner", JobStatus.FINISHED)
        _add_gmx_job(app, experiment_id, "protein.simulation.json", "extension", None)
        _add_gmx_job(app, experiment_id, "protein.simulation.json", "stopped-extension", JobStatus.STOPPED)

    def test_legacy_null_status_rows_are_not_blocked(self, app: Flask, experiment_id: str) -> None:
        """NULL (never-converged) rows stay outside the index so cold-extends are not rejected."""
        _add_gmx_job(app, experiment_id, "protein.simulation.json", "legacy-a", None)
        _add_gmx_job(app, experiment_id, "protein.simulation.json", "legacy-b", None)


class TestSegmentHistory:
    """Segment-scoped routes act on the latest row; DELETE cascades all segments."""

    def test_get_returns_latest_segment(
        self, client: FlaskClient, app: Flask, experiment_id: str, tmp_path: Path, mocker: MockerFixture
    ) -> None:
        _mock_mdrun(mocker)
        sim_path = _write_gmx_simulation(tmp_path / experiment_id)
        _add_gmx_job(
            app, experiment_id, sim_path, "seg-old", JobStatus.STOPPED, created_at=_ONE_HOUR_AGO, _nsteps=100000
        )
        _add_gmx_job(app, experiment_id, sim_path, "seg-new", JobStatus.FINISHED, _nsteps=150000)

        response = client.get(f"/dash/api/experiments/{experiment_id}/gmx/{sim_path}")

        assert response.status_code == HTTPStatus.OK
        assert response.get_json()["id"] == "seg-new"

    def test_delete_cascades_all_segments_and_files(
        self, client: FlaskClient, app: Flask, experiment_id: str, tmp_path: Path, mocker: MockerFixture
    ) -> None:
        mdrun = _mock_mdrun(mocker)
        exp_dir = tmp_path / experiment_id
        sim_path = _write_gmx_simulation(exp_dir)
        _add_gmx_job(app, experiment_id, sim_path, "seg-old", JobStatus.STOPPED, created_at=_ONE_HOUR_AGO)
        _add_gmx_job(app, experiment_id, sim_path, "seg-new", JobStatus.FINISHED)
        trajectory = exp_dir / "production/protein.xtc"
        trajectory.write_text("partial trajectory\n")

        response = client.delete(f"/dash/api/experiments/{experiment_id}/gmx/{sim_path}")

        assert response.status_code == HTTPStatus.NO_CONTENT
        assert {c.args[0] for c in mdrun["delete_gmx"].call_args_list} == {"seg-old", "seg-new"}
        with app.app_context():
            assert GromacsJob.query.filter_by(experiment_id=experiment_id, simulation_path=sim_path).count() == 0
        assert not trajectory.exists(), "delete still wipes result files"
        assert (exp_dir / sim_path).exists(), "delete keeps the manifest"

    def test_stopped_segment_keeps_analyzing(
        self, app: Flask, experiment_id: str, tmp_path: Path, mocker: MockerFixture
    ) -> None:
        from cache import step_status_cache

        _mock_mdrun(mocker)
        sim_path = _write_gmx_simulation(tmp_path / experiment_id)
        _add_gmx_job(app, experiment_id, sim_path, "seg-stopped", JobStatus.STOPPED)

        step_status_cache.clear()
        with app.app_context():
            sim = Simulation.get(experiment_id, sim_path)
            assert sim.step == 3
            assert sim.status == "analyzing"
            assert not sim.live

    def test_running_segment_dominates_stopped_history(
        self, app: Flask, experiment_id: str, tmp_path: Path, mocker: MockerFixture
    ) -> None:
        from cache import step_status_cache

        _mock_mdrun(mocker, status="running")
        sim_path = _write_gmx_simulation(tmp_path / experiment_id)
        _add_gmx_job(app, experiment_id, sim_path, "seg-stopped", JobStatus.STOPPED, created_at=_ONE_HOUR_AGO)
        _add_gmx_job(app, experiment_id, sim_path, "seg-running", JobStatus.RUNNING)

        step_status_cache.clear()
        with app.app_context():
            sim = Simulation.get(experiment_id, sim_path)
            assert (sim.step, sim.status) == (3, "simulating")
            assert sim.live


class TestAppendedLogParsing:
    """Appended multi-segment logs: full-file parsers take the newest segment's values."""

    SEGMENT_1 = "\n".join([
        "Started mdrun on rank 0 Mon Jan 01 10:00:00 2024",
        "            init-step = 0",
        "              nsteps = 100000",
    ])
    SEGMENT_2 = "\n".join([
        "Started mdrun on rank 0 Mon Jan 01 12:00:00 2024",
        "            init-step = 100000",
        "              nsteps = 150000",
    ])

    def _job_with_appended_log(self, app: Flask, exp_id: str, tmp_path: Path) -> GromacsJob:
        exp_dir = tmp_path / exp_id
        sim_path = _write_gmx_simulation(exp_dir)
        (exp_dir / "production/protein.log").write_text(f"{self.SEGMENT_1}\n{self.SEGMENT_2}\n")
        return _add_gmx_job(app, exp_id, sim_path, "seg-2", JobStatus.RUNNING)

    def test_parse_nsteps_last_match(self, app: Flask, experiment_id: str, tmp_path: Path) -> None:
        job = self._job_with_appended_log(app, experiment_id, tmp_path)
        with app.app_context():
            assert job._parse_nsteps() == 150000

    def test_parse_init_step_last_match(self, app: Flask, experiment_id: str, tmp_path: Path) -> None:
        job = self._job_with_appended_log(app, experiment_id, tmp_path)
        with app.app_context():
            assert job._parse_init_step() == 100000

    def test_parse_start_timestamp_last_match(self, app: Flask, experiment_id: str, tmp_path: Path) -> None:
        job = self._job_with_appended_log(app, experiment_id, tmp_path)
        expected = int(datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC).timestamp())
        with app.app_context():
            assert job._parse_start_timestamp() == expected


class TestRoutePathGuards:
    """Unknown verb suffixes must not fall into the greedy submit routes."""

    def test_amber_extend_is_explicitly_gmx_only(
        self, client: FlaskClient, app: Flask, experiment_id: str, tmp_path: Path, mocker: MockerFixture
    ) -> None:
        mdrun = _mock_mdrun(mocker)
        sim_path = _write_amber_simulation(tmp_path / experiment_id)
        _add_amber_job(app, experiment_id, sim_path, "amber-done", JobStatus.FINISHED)

        response = client.post(f"/dash/api/experiments/{experiment_id}/amber/{sim_path}/extend", json={"nsteps": 5000})

        assert response.status_code == HTTPStatus.BAD_REQUEST
        assert "GROMACS" in response.get_json()["detail"]
        mdrun["create"].assert_not_called()

    def test_typo_verb_suffix_gets_404_on_submit(
        self, client: FlaskClient, experiment_id: str, tmp_path: Path, mocker: MockerFixture
    ) -> None:
        _mock_mdrun(mocker)
        _write_gmx_simulation(tmp_path / experiment_id)

        response = client.post(
            f"/dash/api/experiments/{experiment_id}/gmx/protein.simulation.json/stoppe",
            json={"np": 4, "ntomp": 2, "pme": "cpu", "nb": "gpu"},
        )

        assert response.status_code == HTTPStatus.NOT_FOUND


class TestStripRunControlArgs:
    """extra_args composition for extension."""

    def test_strips_nsteps_variants(self) -> None:
        from utils import strip_run_control_args

        assert strip_run_control_args("-nsteps 80000 -ntomp 4") == "-ntomp 4"
        assert strip_run_control_args("-nsteps=80000") == ""
        assert strip_run_control_args("") == ""

    def test_strips_quoted_nsteps_without_dangling_quote(self) -> None:
        """Quoted -nsteps must not leave a dangling quote that breaks MDRun's shlex.split."""
        from utils import strip_run_control_args

        assert strip_run_control_args('-nsteps "1000"') == ""
        assert strip_run_control_args("-nsteps '1000'") == ""
        assert strip_run_control_args('-v -nsteps "1000" -cpt 15') == "-v -cpt 15"

    def test_rejects_cpi(self) -> None:
        from utils import strip_run_control_args

        with pytest.raises(ValueError, match=re.escape("-cpi")):
            strip_run_control_args("-cpi state.cpt")
        with pytest.raises(ValueError, match=re.escape("-cpi")):
            strip_run_control_args("-ntomp 4 -cpi")
