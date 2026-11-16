"""Unit tests for the run lifecycle: non-destructive stop, GMX extension, one run per simulation."""

import json
import re
from datetime import UTC, datetime
from http import HTTPStatus
from pathlib import Path
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from clients import Clients
from clients.mdrun import MDRunClient
from core import db as db_module
from core.enums import AmberBinary, DeviceType, Engine, EwaldPreset, JobStatus
from httpx import AsyncClient
from modules.jobs.amber.models import AmberJob
from modules.jobs.gmx.models import GromacsJob
from modules.jobs.service import JobsService
from modules.models import Experiment
from modules.simulations.manifest import Simulation
from pytest_mock import MockerFixture
from sqlalchemy.ext.asyncio import AsyncSession
from tests.support import SeedExperiment, write_simulation

GMX_INPUTS = ("run_input", "reference_structure")
AMBER_INPUTS = ("topology", "coordinates", "control", "reference_structure")


@pytest.fixture
async def experiment_id(seed_experiment: SeedExperiment) -> str:
    exp_id, _ = await seed_experiment("lifec", name="Lifecycle")
    return exp_id


@pytest.fixture
async def amber_experiment_id(seed_experiment: SeedExperiment) -> str:
    exp_id, _ = await seed_experiment("lifeca", name="Lifecycle AMBER", engine=Engine.AMBER)
    return exp_id


async def _fresh[J: (GromacsJob, AmberJob)](db_session: AsyncSession, model: type[J], job_id: str) -> J | None:
    """Re-read a job row as stored (requests commit through their own sessions)."""
    db_session.expunge_all()
    return (await db_session.execute(model.query().filter_by(id=job_id))).scalars().first()


async def _run(db_session: AsyncSession, experiment_id: str, sim_path: str) -> GromacsJob | None:
    db_session.expunge_all()
    stmt = GromacsJob.query().filter_by(experiment_id=experiment_id, simulation_path=sim_path)
    return (await db_session.execute(stmt)).scalars().first()


async def _runs(db_session: AsyncSession, experiment_id: str, sim_path: str) -> list[GromacsJob]:
    db_session.expunge_all()
    stmt = GromacsJob.query().filter_by(experiment_id=experiment_id, simulation_path=sim_path)
    return list((await db_session.execute(stmt)).scalars().all())


async def _sim(db_session: AsyncSession, clients: Clients, experiment_id: str, sim_path: str) -> Simulation:
    db_session.expunge_all()
    experiment = await db_session.get(Experiment, experiment_id)
    assert experiment is not None
    await JobsService(db_session, clients).refresh(experiment)
    return Simulation.get(experiment_id, sim_path, experiment)


async def _add_gmx_job(
    db_session: AsyncSession,
    exp_id: str,
    simulation_path: str,
    job_id: str,
    status: JobStatus | None = JobStatus.FINISHED,
    **kwargs: object,
) -> GromacsJob:
    """Persist a GromacsJob row without going through MDRun."""
    db_session.add(
        GromacsJob(
            id=job_id,
            experiment_id=exp_id,
            simulation_path=simulation_path,
            np=8,
            ntomp=1,
            pme=DeviceType.CPU,
            nb=DeviceType.GPU,
            _last_known_status=status,
            **kwargs,
        )
    )
    await db_session.commit()
    found = await _fresh(db_session, GromacsJob, job_id)
    assert found is not None
    return found


async def _add_amber_job(
    db_session: AsyncSession, exp_id: str, simulation_path: str, job_id: str, status: JobStatus | None
) -> AmberJob:
    db_session.add(
        AmberJob(
            id=job_id,
            experiment_id=exp_id,
            simulation_path=simulation_path,
            np=1,
            ntomp=8,
            binary=AmberBinary.PMEMD_CUDA,
            ewald=EwaldPreset.DEFAULT,
            _last_known_status=status,
        )
    )
    await db_session.commit()
    found = await _fresh(db_session, AmberJob, job_id)
    assert found is not None
    return found


def _mock_mdrun(mocker: MockerFixture, status: str = "finished") -> dict:
    """Patch every MDRun call the run services make, keyed per engine (`stop` keeps `(job_id, engine)`)."""
    mocks = {
        "get_gmx": AsyncMock(return_value={"id": "x", "status": status}),
        "get_amber": AsyncMock(return_value={"id": "x", "status": status}),
        "create": AsyncMock(side_effect=lambda **_: {"id": str(uuid4()), "status": "running"}),
        "create_amber": AsyncMock(side_effect=lambda **_: {"id": str(uuid4()), "status": "running"}),
        "delete_gmx": AsyncMock(),
        "delete_amber": AsyncMock(),
        "stop": AsyncMock(),
    }

    async def get_job(_client: MDRunClient, engine: str, job_id: str) -> dict:
        return await mocks[f"get_{engine}"](job_id)

    async def delete_job(_client: MDRunClient, engine: str, job_id: str) -> None:
        await mocks[f"delete_{engine}"](job_id)

    async def stop_job(_client: MDRunClient, engine: str, job_id: str) -> None:
        await mocks["stop"](job_id, engine)

    async def create_gmx_job(_client: MDRunClient, **kwargs: object) -> dict:
        return await mocks["create"](**kwargs)

    async def create_amber_job(_client: MDRunClient, **kwargs: object) -> dict:
        return await mocks["create_amber"](**kwargs)

    mocker.patch.multiple(
        MDRunClient,
        get_job=get_job,
        delete_job=delete_job,
        stop_job=stop_job,
        create_gmx_job=create_gmx_job,
        create_amber_job=create_amber_job,
    )
    return mocks


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

    async def test_stop_live_gmx_job(
        self, client: AsyncClient, db_session: AsyncSession, experiment_id: str, tmp_path: Path, mocker: MockerFixture
    ) -> None:
        mdrun = _stop_mocks(mocker)
        sim_path = write_simulation(tmp_path / experiment_id, inputs=GMX_INPUTS)
        job = await _add_gmx_job(db_session, experiment_id, sim_path, "job-live", JobStatus.RUNNING)
        log = tmp_path / experiment_id / "production/protein.log"
        log.write_text("growing log\n")

        response = await client.post(f"/dash/api/experiments/{experiment_id}/gmx/{sim_path}/stop")

        assert response.status_code == HTTPStatus.NO_CONTENT
        mdrun["stop"].assert_called_once_with(job.id, "gmx")
        stopped = await _fresh(db_session, GromacsJob, job.id)
        assert stopped is not None, "row must be kept"
        assert stopped._last_known_status is JobStatus.STOPPED
        assert log.exists(), "result files must survive a stop"

    async def test_stop_keeps_finished_when_the_run_beats_the_stop(
        self, client: AsyncClient, db_session: AsyncSession, experiment_id: str, tmp_path: Path, mocker: MockerFixture
    ) -> None:
        """A job that finishes between the guard and the stop must stay FINISHED, not STOPPED."""
        mdrun = _stop_mocks(mocker)

        def finished_outcome(_job_id: str) -> dict:
            return {"id": _job_id, "status": "finished" if mdrun["stop"].called else "running"}

        mdrun["get_gmx"].side_effect = finished_outcome
        sim_path = write_simulation(tmp_path / experiment_id, inputs=GMX_INPUTS)
        job = await _add_gmx_job(db_session, experiment_id, sim_path, "job-fast", JobStatus.RUNNING)

        response = await client.post(f"/dash/api/experiments/{experiment_id}/gmx/{sim_path}/stop")

        assert response.status_code == HTTPStatus.NO_CONTENT
        row = await _fresh(db_session, GromacsJob, job.id)
        assert row is not None
        assert row._last_known_status is JobStatus.FINISHED

    async def test_stop_terminal_gmx_job_is_400(
        self, client: AsyncClient, db_session: AsyncSession, experiment_id: str, tmp_path: Path, mocker: MockerFixture
    ) -> None:
        _mock_mdrun(mocker)
        sim_path = write_simulation(tmp_path / experiment_id, inputs=GMX_INPUTS)
        await _add_gmx_job(db_session, experiment_id, sim_path, "job-done", JobStatus.FINISHED)

        response = await client.post(f"/dash/api/experiments/{experiment_id}/gmx/{sim_path}/stop")

        assert response.status_code == HTTPStatus.BAD_REQUEST

    async def test_stop_gmx_missing_job_is_404(self, client: AsyncClient, experiment_id: str) -> None:
        response = await client.post(f"/dash/api/experiments/{experiment_id}/gmx/nope.simulation.json/stop")

        assert response.status_code == HTTPStatus.NOT_FOUND

    async def test_stop_live_amber_job(
        self, client: AsyncClient, db_session: AsyncSession, experiment_id: str, tmp_path: Path, mocker: MockerFixture
    ) -> None:
        mdrun = _stop_mocks(mocker, engine="amber")
        sim_path = write_simulation(
            tmp_path / experiment_id, "prod.simulation.json", engine=Engine.AMBER, name="prod", inputs=AMBER_INPUTS
        )
        job = await _add_amber_job(db_session, experiment_id, sim_path, "amber-live", JobStatus.RUNNING)

        response = await client.post(f"/dash/api/experiments/{experiment_id}/amber/{sim_path}/stop")

        assert response.status_code == HTTPStatus.NO_CONTENT
        mdrun["stop"].assert_called_once_with(job.id, "amber")
        stopped = await _fresh(db_session, AmberJob, job.id)
        assert stopped is not None
        assert stopped._last_known_status is JobStatus.STOPPED


class TestSubmit:
    """Submit starts a run: a live run 409s; a terminal run's history is deleted and replaced."""

    async def test_submit_creates_job_on_empty_history(
        self, client: AsyncClient, experiment_id: str, tmp_path: Path, mocker: MockerFixture
    ) -> None:
        mdrun = _mock_mdrun(mocker)
        sim_path = write_simulation(tmp_path / experiment_id, inputs=GMX_INPUTS)

        response = await client.post(
            f"/dash/api/experiments/{experiment_id}/gmx/{sim_path}",
            json={"np": 4, "ntomp": 2, "pme": "cpu", "nb": "gpu"},
        )

        assert response.status_code == HTTPStatus.CREATED
        mdrun["create"].assert_called_once()

    async def test_submit_race_loser_gets_409_and_its_mdrun_job_is_deleted(
        self, client: AsyncClient, db_session: AsyncSession, experiment_id: str, tmp_path: Path, mocker: MockerFixture
    ) -> None:
        """A concurrent submit committing first wins; the loser rolls back and tears down its MDRun job."""
        mdrun = _mock_mdrun(mocker)
        sim_path = write_simulation(tmp_path / experiment_id, inputs=GMX_INPUTS)

        async def concurrent_winner(**kwargs: object) -> dict:
            async with db_module.session_factory()() as rival_session:
                rival_session.add(
                    GromacsJob(
                        id="rival-run",
                        experiment_id=experiment_id,
                        simulation_path=sim_path,
                        np=8,
                        ntomp=1,
                        pme=DeviceType.CPU,
                        nb=DeviceType.GPU,
                        engine=Engine.GMX,
                        _last_known_status=JobStatus.PENDING,
                    )
                )
                await rival_session.commit()
            return {"id": "losing-run", "status": "running"}

        mdrun["create"].side_effect = concurrent_winner

        response = await client.post(
            f"/dash/api/experiments/{experiment_id}/gmx/{sim_path}",
            json={"np": 4, "ntomp": 2, "pme": "cpu", "nb": "gpu"},
        )

        assert response.status_code == HTTPStatus.CONFLICT
        mdrun["delete_gmx"].assert_called_once_with("losing-run")
        assert {j.id for j in await _runs(db_session, experiment_id, sim_path)} == {"rival-run"}

    @pytest.mark.parametrize("status", [JobStatus.PENDING, JobStatus.RUNNING])
    async def test_submit_live_run_conflicts(
        self,
        status: JobStatus,
        client: AsyncClient,
        db_session: AsyncSession,
        experiment_id: str,
        tmp_path: Path,
        mocker: MockerFixture,
    ) -> None:
        """A live run blocks submit until it is stopped."""
        mdrun = _mock_mdrun(mocker, status="running")
        sim_path = write_simulation(tmp_path / experiment_id, inputs=GMX_INPUTS)
        await _add_gmx_job(db_session, experiment_id, sim_path, f"job-{status.value}", status)

        response = await client.post(
            f"/dash/api/experiments/{experiment_id}/gmx/{sim_path}",
            json={"np": 4, "ntomp": 2, "pme": "cpu", "nb": "gpu"},
        )

        assert response.status_code == HTTPStatus.CONFLICT
        assert (
            response.json()["detail"]
            == "A run is already active for this simulation; stop it first to submit a new run."
        )
        mdrun["create"].assert_not_called()
        assert await _fresh(db_session, GromacsJob, f"job-{status.value}") is not None, "live row must survive"

    @pytest.mark.parametrize("status", [JobStatus.STOPPED, JobStatus.FINISHED, JobStatus.ERROR])
    async def test_submit_replaces_terminal_run(
        self,
        status: JobStatus,
        client: AsyncClient,
        db_session: AsyncSession,
        experiment_id: str,
        tmp_path: Path,
        mocker: MockerFixture,
    ) -> None:
        """A finished, stopped, or failed run is deleted and the new run starts with fresh params."""
        mdrun = _mock_mdrun(mocker)
        sim_path = write_simulation(tmp_path / experiment_id, inputs=GMX_INPUTS)
        await _add_gmx_job(db_session, experiment_id, sim_path, f"job-{status.value}", status)

        response = await client.post(
            f"/dash/api/experiments/{experiment_id}/gmx/{sim_path}",
            json={"np": 4, "ntomp": 2, "pme": "cpu", "nb": "gpu"},
        )

        assert response.status_code == HTTPStatus.CREATED
        mdrun["delete_gmx"].assert_called_once_with(f"job-{status.value}")
        mdrun["create"].assert_called_once()
        assert await _fresh(db_session, GromacsJob, f"job-{status.value}") is None, "old row must be gone"
        assert await _fresh(db_session, GromacsJob, response.json()["id"]) is not None

    async def test_submit_replaces_terminal_amber_run(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        amber_experiment_id: str,
        tmp_path: Path,
        mocker: MockerFixture,
    ) -> None:
        mdrun = _mock_mdrun(mocker)
        sim_path = write_simulation(
            tmp_path / amber_experiment_id,
            "prod.simulation.json",
            engine=Engine.AMBER,
            name="prod",
            inputs=AMBER_INPUTS,
        )
        await _add_amber_job(db_session, amber_experiment_id, sim_path, "amber-fin", JobStatus.FINISHED)

        response = await client.post(
            f"/dash/api/experiments/{amber_experiment_id}/amber/{sim_path}",
            json={"binary": "pmemd.cuda", "ewald": "default", "np": 1, "ntomp": 8},
        )

        assert response.status_code == HTTPStatus.CREATED
        mdrun["delete_amber"].assert_called_once_with("amber-fin")
        mdrun["create_amber"].assert_called_once()
        assert await _fresh(db_session, AmberJob, "amber-fin") is None, "old row must be gone"

    async def test_resubmit_after_delete_succeeds(
        self, client: AsyncClient, db_session: AsyncSession, experiment_id: str, tmp_path: Path, mocker: MockerFixture
    ) -> None:
        """The sanctioned re-run path: DELETE wipes the history, then POST creates a fresh run."""
        mdrun = _mock_mdrun(mocker)
        sim_path = write_simulation(tmp_path / experiment_id, inputs=GMX_INPUTS)
        await _add_gmx_job(db_session, experiment_id, sim_path, "job-old", JobStatus.STOPPED)

        assert (
            await client.delete(f"/dash/api/experiments/{experiment_id}/gmx/{sim_path}")
        ).status_code == HTTPStatus.NO_CONTENT

        response = await client.post(
            f"/dash/api/experiments/{experiment_id}/gmx/{sim_path}",
            json={"np": 4, "ntomp": 2, "pme": "cpu", "nb": "gpu"},
        )

        assert response.status_code == HTTPStatus.CREATED
        mdrun["create"].assert_called_once()


class TestExtend:
    """mdrun -cpi counts ADDITIONAL steps: commands carry the delta, the run row persists the absolute target."""

    async def _setup_finished_run(
        self, db_session: AsyncSession, exp_id: str, tmp_path: Path, extra_args: str = "", **job_kwargs: object
    ) -> str:
        sim_path = write_simulation(tmp_path / exp_id, inputs=GMX_INPUTS, extra_args=extra_args)
        await _add_gmx_job(db_session, exp_id, sim_path, "run-1", JobStatus.FINISHED, **job_kwargs)
        return sim_path

    def _write_checkpoint(self, exp_dir: Path) -> None:
        (exp_dir / "production/protein.cpt").write_bytes(b"cpt\n")

    async def test_extend_replaces_run_with_composed_args(
        self, client: AsyncClient, db_session: AsyncSession, experiment_id: str, tmp_path: Path, mocker: MockerFixture
    ) -> None:
        mdrun = _mock_mdrun(mocker)
        sim_path = await self._setup_finished_run(
            db_session, experiment_id, tmp_path, _nsteps=100000, _performance=68.5
        )
        self._write_checkpoint(tmp_path / experiment_id)

        response = await client.post(
            f"/dash/api/experiments/{experiment_id}/gmx/{sim_path}/extend", json={"nsteps": 50000}
        )

        assert response.status_code == HTTPStatus.CREATED
        kwargs = mdrun["create"].call_args.kwargs
        assert kwargs["tpr_name"] == "production/protein.tpr"
        # The command carries the delta…
        assert kwargs["extra_args"] == "-cpi protein.cpt -nsteps 50000"
        # Hardware inherited from the finished run.
        assert (kwargs["pme"], kwargs["nb"], kwargs["np"], kwargs["ntomp"]) == ("cpu", "gpu", 8, 1)
        # Manifest itself stays untouched.
        manifest = json.loads((tmp_path / experiment_id / sim_path).read_text())
        assert manifest["extra_args"] == ""

        run = await _run(db_session, experiment_id, sim_path)
        assert run is not None
        # The row is swapped in place: one run, PK naming the new MDRun job…
        assert run.id == response.json()["id"] != "run-1"
        # …while the row persists the absolute end target for the display.
        assert run._nsteps == 150000

    async def test_extend_respects_manifest_nsteps_override(
        self, client: AsyncClient, db_session: AsyncSession, experiment_id: str, tmp_path: Path, mocker: MockerFixture
    ) -> None:
        mdrun = _mock_mdrun(mocker)
        sim_path = await self._setup_finished_run(db_session, experiment_id, tmp_path, extra_args="-nsteps 80000")
        self._write_checkpoint(tmp_path / experiment_id)

        response = await client.post(
            f"/dash/api/experiments/{experiment_id}/gmx/{sim_path}/extend", json={"nsteps": 50000}
        )

        assert response.status_code == HTTPStatus.CREATED
        kwargs = mdrun["create"].call_args.kwargs
        # The stale override is stripped; mdrun gets only the requested delta.
        assert kwargs["extra_args"] == "-cpi protein.cpt -nsteps 50000"

    async def test_extend_chains_cumulative_totals(
        self, client: AsyncClient, db_session: AsyncSession, experiment_id: str, tmp_path: Path, mocker: MockerFixture
    ) -> None:
        """Each extension persists its absolute end target; each command carries just its delta."""
        mdrun = _mock_mdrun(mocker)
        sim_path = await self._setup_finished_run(
            db_session, experiment_id, tmp_path, _nsteps=100000, _performance=68.5
        )
        self._write_checkpoint(tmp_path / experiment_id)

        await client.post(f"/dash/api/experiments/{experiment_id}/gmx/{sim_path}/extend", json={"nsteps": 50000})
        # The extended run finishes (its MDRun entry reports finished), then extends again.
        run = await _run(db_session, experiment_id, sim_path)
        assert run is not None
        run._last_known_status = JobStatus.FINISHED
        await db_session.commit()

        response = await client.post(
            f"/dash/api/experiments/{experiment_id}/gmx/{sim_path}/extend", json={"nsteps": 25000}
        )

        assert response.status_code == HTTPStatus.CREATED
        kwargs = mdrun["create"].call_args.kwargs
        assert kwargs["extra_args"] == "-cpi protein.cpt -nsteps 25000"
        run = await _run(db_session, experiment_id, sim_path)
        assert run is not None
        assert run._nsteps == 175000
        assert len(await _runs(db_session, experiment_id, sim_path)) == 1

    async def test_extend_chains_persisted_total_over_stale_manifest_override(
        self, client: AsyncClient, db_session: AsyncSession, experiment_id: str, tmp_path: Path, mocker: MockerFixture
    ) -> None:
        """A second extension must build on the persisted cumulative target, never the manifest's stale -nsteps."""
        mdrun = _mock_mdrun(mocker)
        sim_path = await self._setup_finished_run(db_session, experiment_id, tmp_path, extra_args="-nsteps 80000")
        self._write_checkpoint(tmp_path / experiment_id)

        first = await client.post(
            f"/dash/api/experiments/{experiment_id}/gmx/{sim_path}/extend", json={"nsteps": 50000}
        )
        assert first.status_code == HTTPStatus.CREATED

        # The extension finishes, then a second extension follows.
        run = await _run(db_session, experiment_id, sim_path)
        assert run is not None
        run._last_known_status = JobStatus.FINISHED
        await db_session.commit()

        second = await client.post(
            f"/dash/api/experiments/{experiment_id}/gmx/{sim_path}/extend", json={"nsteps": 25000}
        )

        assert second.status_code == HTTPStatus.CREATED
        kwargs = mdrun["create"].call_args.kwargs
        # The command carries the delta; the row's base remains the first
        # extension's persisted 130000 — NOT the manifest's stale 80000 override.
        assert kwargs["extra_args"] == "-cpi protein.cpt -nsteps 25000"
        run = await _run(db_session, experiment_id, sim_path)
        assert run is not None
        assert run._nsteps == 155000

    async def test_extend_anchors_on_actual_progress_not_target(
        self, client: AsyncClient, db_session: AsyncSession, experiment_id: str, tmp_path: Path, mocker: MockerFixture
    ) -> None:
        """A run stopped short of its target extends from where it stood, not from the target."""
        mdrun = _mock_mdrun(mocker)
        sim_path = await self._setup_finished_run(db_session, experiment_id, tmp_path, _nsteps=150000)
        # Stopped at 120k out of the 150k target — the log tail holds the truth.
        run = await _fresh(db_session, GromacsJob, "run-1")
        assert run is not None
        run._last_known_status = JobStatus.STOPPED
        await db_session.commit()
        (tmp_path / experiment_id / "production/protein.log").write_text(
            "header\n        120000    2400000.0000     1000.0000\n"
        )
        self._write_checkpoint(tmp_path / experiment_id)

        response = await client.post(
            f"/dash/api/experiments/{experiment_id}/gmx/{sim_path}/extend", json={"nsteps": 20000}
        )

        assert response.status_code == HTTPStatus.CREATED
        kwargs = mdrun["create"].call_args.kwargs
        # The command carries the delta; the new row's base is 120000 done,
        # NOT the 150000 target.
        assert kwargs["extra_args"] == "-cpi protein.cpt -nsteps 20000"
        run = await _run(db_session, experiment_id, sim_path)
        assert run is not None
        assert run._nsteps == 140000
        assert run._init_step == 120000

    async def test_extend_persists_resume_point_as_init_step(
        self, client: AsyncClient, db_session: AsyncSession, experiment_id: str, tmp_path: Path, mocker: MockerFixture
    ) -> None:
        """The appended log never re-dumps init-step, so ETA math needs the resume point persisted."""
        _mock_mdrun(mocker)
        sim_path = await self._setup_finished_run(db_session, experiment_id, tmp_path, _nsteps=150000)
        run = await _fresh(db_session, GromacsJob, "run-1")
        assert run is not None
        run._last_known_status = JobStatus.STOPPED
        await db_session.commit()
        (tmp_path / experiment_id / "production/protein.log").write_text(
            "header\n        120000    2400000.0000     1000.0000\n"
        )
        self._write_checkpoint(tmp_path / experiment_id)

        response = await client.post(
            f"/dash/api/experiments/{experiment_id}/gmx/{sim_path}/extend", json={"nsteps": 20000}
        )

        assert response.status_code == HTTPStatus.CREATED
        run = await _run(db_session, experiment_id, sim_path)
        assert run is not None
        assert run._init_step == 120000
        assert run.init_step == 120000

    async def test_extend_anchors_on_step_rows_despite_stop_performance_block(
        self, client: AsyncClient, db_session: AsyncSession, experiment_id: str, tmp_path: Path, mocker: MockerFixture
    ) -> None:
        """A real TERM-stopped run prints Performance: too — it must neither shortcut the row nor be cached."""
        mdrun = _mock_mdrun(mocker)
        sim_path = await self._setup_finished_run(db_session, experiment_id, tmp_path, _nsteps=150000)
        run = await _fresh(db_session, GromacsJob, "run-1")
        assert run is not None
        run._last_known_status = JobStatus.STOPPED
        await db_session.commit()
        # Real TERM-stop trailer: step rows up to 120k, then a Performance: line.
        (tmp_path / experiment_id / "production/protein.log").write_text(
            "header\n        120000    2400000.0000     1000.0000\nPerformance:        61.2\n"
        )
        self._write_checkpoint(tmp_path / experiment_id)

        response = await client.post(
            f"/dash/api/experiments/{experiment_id}/gmx/{sim_path}/extend", json={"nsteps": 20000}
        )

        assert response.status_code == HTTPStatus.CREATED
        assert mdrun["create"].call_args.kwargs["extra_args"] == "-cpi protein.cpt -nsteps 20000"
        run = await _run(db_session, experiment_id, sim_path)
        assert run is not None
        # Stopped is not a proven 150k completion; the anchor is the log's 120k,
        # and no performance is inherited onto the new row.
        assert run._init_step == 120000
        assert run.nsteps_done == 120000
        assert run.performance is None
        assert run._performance is None

    async def test_extend_falls_back_to_target_when_progress_unparseable(
        self, client: AsyncClient, db_session: AsyncSession, experiment_id: str, tmp_path: Path, mocker: MockerFixture
    ) -> None:
        """With no parseable step rows (e.g. missing log), the anchor falls back to the target."""
        mdrun = _mock_mdrun(mocker)
        sim_path = await self._setup_finished_run(db_session, experiment_id, tmp_path, _nsteps=150000)
        run = await _fresh(db_session, GromacsJob, "run-1")
        assert run is not None
        run._last_known_status = JobStatus.STOPPED
        await db_session.commit()
        self._write_checkpoint(tmp_path / experiment_id)

        response = await client.post(
            f"/dash/api/experiments/{experiment_id}/gmx/{sim_path}/extend", json={"nsteps": 20000}
        )

        assert response.status_code == HTTPStatus.CREATED
        assert mdrun["create"].call_args.kwargs["extra_args"] == "-cpi protein.cpt -nsteps 20000"
        run = await _run(db_session, experiment_id, sim_path)
        assert run is not None
        assert run._nsteps == 170000
        assert run._init_step == 150000

    async def test_extend_finished_50k_by_10_runs_exactly_10_more_steps(
        self, client: AsyncClient, db_session: AsyncSession, experiment_id: str, tmp_path: Path, mocker: MockerFixture
    ) -> None:
        """A finished run extended by N runs exactly N more steps, ending at base + N."""
        mdrun = _mock_mdrun(mocker)
        sim_path = await self._setup_finished_run(db_session, experiment_id, tmp_path, _nsteps=50000, _performance=68.5)
        self._write_checkpoint(tmp_path / experiment_id)

        response = await client.post(
            f"/dash/api/experiments/{experiment_id}/gmx/{sim_path}/extend", json={"nsteps": 10}
        )

        assert response.status_code == HTTPStatus.CREATED
        kwargs = mdrun["create"].call_args.kwargs
        assert kwargs["extra_args"] == "-cpi protein.cpt -nsteps 10"
        run = await _run(db_session, experiment_id, sim_path)
        assert run is not None
        assert run.nsteps == 50010

    async def test_extend_race_loser_gets_400_and_its_mdrun_job_is_deleted(
        self, client: AsyncClient, db_session: AsyncSession, experiment_id: str, tmp_path: Path, mocker: MockerFixture
    ) -> None:
        """A concurrent extension winning between the live check and our row swap is rejected atomically."""
        mdrun = _mock_mdrun(mocker)
        sim_path = await self._setup_finished_run(
            db_session, experiment_id, tmp_path, _nsteps=100000, _performance=68.5
        )
        self._write_checkpoint(tmp_path / experiment_id)

        async def concurrent_winner(**kwargs: object) -> dict:
            # A concurrent request replaces the run after our is_live check but
            # before our insert, exactly the window the unique constraint closes.
            async with db_module.session_factory()() as rival_session:
                base = await rival_session.get(GromacsJob, "run-1")
                assert base is not None
                await rival_session.delete(base)
                await rival_session.flush()
                rival_session.add(
                    GromacsJob(
                        id="rival-run",
                        experiment_id=experiment_id,
                        simulation_path=sim_path,
                        np=8,
                        ntomp=1,
                        pme=DeviceType.CPU,
                        nb=DeviceType.GPU,
                        engine=Engine.GMX,
                        _last_known_status=JobStatus.PENDING,
                    )
                )
                await rival_session.commit()
            return {"id": "losing-run", "status": "running"}

        mdrun["create"].side_effect = concurrent_winner

        response = await client.post(
            f"/dash/api/experiments/{experiment_id}/gmx/{sim_path}/extend", json={"nsteps": 50000}
        )

        assert response.status_code == HTTPStatus.BAD_REQUEST
        assert "already in progress" in response.json()["detail"]
        # The orphaned cluster job behind the losing insert is torn down.
        mdrun["delete_gmx"].assert_called_once_with("losing-run")
        ids = {j.id for j in await _runs(db_session, experiment_id, sim_path)}
        assert ids == {"rival-run"}, "the losing replacement must be rolled back"

    async def test_extend_rejects_manifest_with_cpi(
        self, client: AsyncClient, db_session: AsyncSession, experiment_id: str, tmp_path: Path, mocker: MockerFixture
    ) -> None:
        mdrun = _mock_mdrun(mocker)
        sim_path = await self._setup_finished_run(db_session, experiment_id, tmp_path, extra_args="-cpi state.cpt")
        self._write_checkpoint(tmp_path / experiment_id)

        response = await client.post(
            f"/dash/api/experiments/{experiment_id}/gmx/{sim_path}/extend", json={"nsteps": 50000}
        )

        assert response.status_code == HTTPStatus.BAD_REQUEST
        mdrun["create"].assert_not_called()

    async def test_extend_requires_checkpoint(
        self, client: AsyncClient, db_session: AsyncSession, experiment_id: str, tmp_path: Path, mocker: MockerFixture
    ) -> None:
        mdrun = _mock_mdrun(mocker)
        sim_path = await self._setup_finished_run(db_session, experiment_id, tmp_path, _nsteps=100000)

        response = await client.post(
            f"/dash/api/experiments/{experiment_id}/gmx/{sim_path}/extend", json={"nsteps": 50000}
        )

        assert response.status_code == HTTPStatus.BAD_REQUEST
        assert "checkpoint" in response.json()["detail"].lower()
        mdrun["create"].assert_not_called()

    async def test_extend_rejects_live_run(
        self, client: AsyncClient, db_session: AsyncSession, experiment_id: str, tmp_path: Path, mocker: MockerFixture
    ) -> None:
        mdrun = _mock_mdrun(mocker, status="running")
        sim_path = write_simulation(tmp_path / experiment_id, inputs=GMX_INPUTS)
        await _add_gmx_job(db_session, experiment_id, sim_path, "run-live", JobStatus.RUNNING)
        self._write_checkpoint(tmp_path / experiment_id)

        response = await client.post(
            f"/dash/api/experiments/{experiment_id}/gmx/{sim_path}/extend", json={"nsteps": 50000}
        )

        assert response.status_code == HTTPStatus.BAD_REQUEST
        mdrun["create"].assert_not_called()

    async def test_extend_requires_existing_run(
        self, client: AsyncClient, db_session: AsyncSession, experiment_id: str, tmp_path: Path, mocker: MockerFixture
    ) -> None:
        _mock_mdrun(mocker)
        sim_path = write_simulation(tmp_path / experiment_id, inputs=GMX_INPUTS)
        self._write_checkpoint(tmp_path / experiment_id)

        response = await client.post(
            f"/dash/api/experiments/{experiment_id}/gmx/{sim_path}/extend", json={"nsteps": 50000}
        )

        assert response.status_code == HTTPStatus.BAD_REQUEST

    @pytest.mark.parametrize("nsteps", ["abc", 0, -5, None])
    async def test_extend_rejects_invalid_nsteps(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        experiment_id: str,
        tmp_path: Path,
        mocker: MockerFixture,
        nsteps: object,
    ) -> None:
        _mock_mdrun(mocker)
        sim_path = await self._setup_finished_run(db_session, experiment_id, tmp_path, _nsteps=100000)
        self._write_checkpoint(tmp_path / experiment_id)

        response = await client.post(
            f"/dash/api/experiments/{experiment_id}/gmx/{sim_path}/extend", json={"nsteps": nsteps}
        )

        assert response.status_code == HTTPStatus.BAD_REQUEST


class TestRunUniqueness:
    """DB-level guarantee: one run row per simulation, whatever its status."""

    @pytest.mark.parametrize(
        "winner_status",
        [JobStatus.PENDING, JobStatus.RUNNING, JobStatus.UNKNOWN, JobStatus.FINISHED, JobStatus.STOPPED, None],
    )
    async def test_second_run_row_is_rejected(
        self, db_session: AsyncSession, experiment_id: str, winner_status: JobStatus | None
    ) -> None:
        from sqlalchemy.exc import IntegrityError

        await _add_gmx_job(db_session, experiment_id, "protein.simulation.json", "winner", winner_status)
        with pytest.raises(IntegrityError):
            await _add_gmx_job(db_session, experiment_id, "protein.simulation.json", "rival", JobStatus.PENDING)


class TestRunRow:
    """Run routes act on the simulation's single run row."""

    async def test_get_returns_the_run(
        self, client: AsyncClient, db_session: AsyncSession, experiment_id: str, tmp_path: Path, mocker: MockerFixture
    ) -> None:
        _mock_mdrun(mocker)
        sim_path = write_simulation(tmp_path / experiment_id, inputs=GMX_INPUTS)
        await _add_gmx_job(db_session, experiment_id, sim_path, "the-run", JobStatus.FINISHED, _nsteps=150000)

        response = await client.get(f"/dash/api/experiments/{experiment_id}/gmx/{sim_path}")

        assert response.status_code == HTTPStatus.OK
        assert response.json()["id"] == "the-run"

    async def test_delete_removes_run_and_files(
        self, client: AsyncClient, db_session: AsyncSession, experiment_id: str, tmp_path: Path, mocker: MockerFixture
    ) -> None:
        mdrun = _mock_mdrun(mocker)
        exp_dir = tmp_path / experiment_id
        sim_path = write_simulation(exp_dir, inputs=GMX_INPUTS)
        await _add_gmx_job(db_session, experiment_id, sim_path, "the-run", JobStatus.FINISHED)
        trajectory = exp_dir / "production/protein.xtc"
        trajectory.write_text("partial trajectory\n")

        response = await client.delete(f"/dash/api/experiments/{experiment_id}/gmx/{sim_path}")

        assert response.status_code == HTTPStatus.NO_CONTENT
        mdrun["delete_gmx"].assert_called_once_with("the-run")
        assert len(await _runs(db_session, experiment_id, sim_path)) == 0
        assert not trajectory.exists(), "delete still wipes result files"
        assert (exp_dir / sim_path).exists(), "delete keeps the manifest"

    async def test_stopped_run_keeps_analyzing(
        self,
        db_session: AsyncSession,
        experiment_id: str,
        tmp_path: Path,
        mocker: MockerFixture,
        clients: Clients,
    ) -> None:
        _mock_mdrun(mocker)
        sim_path = write_simulation(tmp_path / experiment_id, inputs=GMX_INPUTS)
        await _add_gmx_job(db_session, experiment_id, sim_path, "run-stopped", JobStatus.STOPPED)

        sim = await _sim(db_session, clients, experiment_id, sim_path)
        assert sim.step == 3
        assert sim.status == "analyzing"
        assert not sim.live

    async def test_running_run_is_live(
        self,
        db_session: AsyncSession,
        experiment_id: str,
        tmp_path: Path,
        mocker: MockerFixture,
        clients: Clients,
    ) -> None:
        _mock_mdrun(mocker, status="running")
        sim_path = write_simulation(tmp_path / experiment_id, inputs=GMX_INPUTS)
        await _add_gmx_job(db_session, experiment_id, sim_path, "run-running", JobStatus.RUNNING)

        sim = await _sim(db_session, clients, experiment_id, sim_path)
        assert (sim.step, sim.status) == (2, "simulating")
        assert sim.live


class TestAppendedLogParsing:
    """Logs appended across extensions: full-file parsers take the newest values."""

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

    async def _job_with_appended_log(self, db_session: AsyncSession, exp_id: str, tmp_path: Path) -> GromacsJob:
        exp_dir = tmp_path / exp_id
        sim_path = write_simulation(exp_dir, inputs=GMX_INPUTS)
        (exp_dir / "production/protein.log").write_text(f"{self.SEGMENT_1}\n{self.SEGMENT_2}\n")
        return await _add_gmx_job(db_session, exp_id, sim_path, "run-2", JobStatus.RUNNING)

    async def test_parse_nsteps_last_match(self, db_session: AsyncSession, experiment_id: str, tmp_path: Path) -> None:
        job = await self._job_with_appended_log(db_session, experiment_id, tmp_path)
        assert job._parse_nsteps() == 150000

    async def test_parse_init_step_last_match(
        self, db_session: AsyncSession, experiment_id: str, tmp_path: Path
    ) -> None:
        job = await self._job_with_appended_log(db_session, experiment_id, tmp_path)
        assert job._parse_init_step() == 100000

    async def test_parse_start_timestamp_last_match(
        self, db_session: AsyncSession, experiment_id: str, tmp_path: Path
    ) -> None:
        job = await self._job_with_appended_log(db_session, experiment_id, tmp_path)
        expected = int(datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC).timestamp())
        assert job._parse_start_timestamp() == expected


class TestRoutePathGuards:
    """Unknown verb suffixes must not fall into the greedy submit routes."""

    async def test_amber_extend_is_explicitly_gmx_only(
        self, client: AsyncClient, db_session: AsyncSession, experiment_id: str, tmp_path: Path, mocker: MockerFixture
    ) -> None:
        mdrun = _mock_mdrun(mocker)
        sim_path = write_simulation(
            tmp_path / experiment_id, "prod.simulation.json", engine=Engine.AMBER, name="prod", inputs=AMBER_INPUTS
        )
        await _add_amber_job(db_session, experiment_id, sim_path, "amber-done", JobStatus.FINISHED)

        response = await client.post(
            f"/dash/api/experiments/{experiment_id}/amber/{sim_path}/extend", json={"nsteps": 5000}
        )

        assert response.status_code == HTTPStatus.BAD_REQUEST
        assert "GROMACS" in response.json()["detail"]
        mdrun["create"].assert_not_called()

    async def test_typo_verb_suffix_gets_404_on_submit(
        self, client: AsyncClient, experiment_id: str, tmp_path: Path, mocker: MockerFixture
    ) -> None:
        _mock_mdrun(mocker)
        write_simulation(tmp_path / experiment_id, inputs=GMX_INPUTS)

        response = await client.post(
            f"/dash/api/experiments/{experiment_id}/gmx/protein.simulation.json/stoppe",
            json={"np": 4, "ntomp": 2, "pme": "cpu", "nb": "gpu"},
        )

        assert response.status_code == HTTPStatus.NOT_FOUND


class TestStripRunControlArgs:
    """extra_args composition for extension."""

    async def test_strips_nsteps_variants(self) -> None:
        from core.utils import strip_run_control_args

        assert strip_run_control_args("-nsteps 80000 -ntomp 4") == "-ntomp 4"
        assert strip_run_control_args("-nsteps=80000") == ""
        assert strip_run_control_args("") == ""

    async def test_strips_quoted_nsteps_without_dangling_quote(self) -> None:
        """Quoted -nsteps must not leave a dangling quote that breaks MDRun's shlex.split."""
        from core.utils import strip_run_control_args

        assert strip_run_control_args('-nsteps "1000"') == ""
        assert strip_run_control_args("-nsteps '1000'") == ""
        assert strip_run_control_args('-v -nsteps "1000" -cpt 15') == "-v -cpt 15"

    async def test_rejects_cpi(self) -> None:
        from core.utils import strip_run_control_args

        with pytest.raises(ValueError, match=re.escape("-cpi")):
            strip_run_control_args("-cpi state.cpt")
        with pytest.raises(ValueError, match=re.escape("-cpi")):
            strip_run_control_args("-ntomp 4 -cpi")
