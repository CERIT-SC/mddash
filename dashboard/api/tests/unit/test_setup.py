"""Headless setup runs: Job/doc reconciliation, start guards, stop, and the routes."""

import json
from pathlib import Path
from types import SimpleNamespace
from typing import TYPE_CHECKING, cast
from unittest.mock import AsyncMock, patch

import pytest
from core.errors import ApiError, Forbidden
from httpx import AsyncClient
from modules.setup.schemas import SetupRunError, SetupState
from modules.setup.service import JobView, SetupService, job_name, reconcile, status_path
from tests.support import SeedExperiment, write_simulation

if TYPE_CHECKING:
    from clients import Clients
    from modules.models import Experiment

NB = "setup.ipynb"
RUNNING_DOC = {"state": "running", "step": 4, "total": 11, "title": "Solvate", "manifests": []}


def _experiment(exp_id: str) -> "Experiment":
    return cast("Experiment", SimpleNamespace(id=exp_id, engine=SimpleNamespace(value="GMX")))


class TestReconcile:
    """One row per state in the spec's Setup card table."""

    def test_never_ran(self) -> None:
        assert reconcile(NB, None, None, has_valid_manifest=False) is None

    def test_starting_until_the_doc_appears(self) -> None:
        run = reconcile(NB, JobView(live=True, waiting=True), None, has_valid_manifest=False)
        assert run is not None
        assert (run.state, run.waiting) == (SetupState.STARTING, True)

    def test_running_reports_the_docs_progress(self) -> None:
        run = reconcile(NB, JobView(live=True), RUNNING_DOC, has_valid_manifest=False)
        assert run is not None
        assert (run.state, run.step, run.total, run.title) == (SetupState.RUNNING, 4, 11, "Solvate")

    def test_done_needs_a_valid_manifest(self) -> None:
        doc = {**RUNNING_DOC, "state": "done", "manifests": ["md.simulation.json"]}
        done = reconcile(NB, None, doc, has_valid_manifest=True)
        assert done is not None
        assert done.state == SetupState.DONE

        run = reconcile(NB, None, doc, has_valid_manifest=False)
        assert run is not None
        assert run.state == SetupState.FAILED
        assert run.error is not None
        assert run.error.message == "Setup finished without writing a simulation manifest."

    def test_failed_shows_the_notebooks_own_error(self) -> None:
        doc = {
            **RUNNING_DOC,
            "state": "failed",
            "error": {"step": 4, "cell": 9, "ename": "ValueError", "evalue": "bad"},
        }
        run = reconcile(NB, JobView(live=False, failed=True), doc, has_valid_manifest=False)
        assert run is not None
        assert run.error is not None
        assert (run.state, run.error.step, run.error.title, run.error.message) == (
            SetupState.FAILED,
            4,
            "Solvate",
            "ValueError: bad",
        )

    def test_stopped(self) -> None:
        run = reconcile(NB, None, {**RUNNING_DOC, "state": "stopped"}, has_valid_manifest=False)
        assert run is not None
        assert run.state == SetupState.STOPPED

    def test_a_vanished_job_with_a_running_doc_was_interrupted(self) -> None:
        run = reconcile(NB, None, RUNNING_DOC, has_valid_manifest=False)
        assert run is not None
        assert run.error is not None
        assert (run.state, run.error.message) == (SetupState.FAILED, "Setup was interrupted.")

    def test_infrastructure_failures_are_friendly(self) -> None:
        oom = JobView(live=False, failed=True, infra_error=SetupRunError(message="Setup ran out of memory."))
        run = reconcile(NB, oom, RUNNING_DOC, has_valid_manifest=False)
        assert run is not None
        assert run.state == SetupState.FAILED
        assert run.error is not None
        assert run.error.message == "Setup ran out of memory."


def _job(conditions: list[SimpleNamespace] | None = None) -> SimpleNamespace:
    return SimpleNamespace(status=SimpleNamespace(conditions=conditions))


@pytest.fixture
def k8s() -> AsyncMock:
    k8s = AsyncMock()
    k8s.read_job.return_value = None
    k8s.list_pods_by_label.return_value = []
    k8s.check_quota_headroom.return_value = None
    k8s.wait_for_resource_absence.return_value = True
    return k8s


@pytest.fixture
def service(k8s: AsyncMock) -> SetupService:
    return SetupService(cast("Clients", SimpleNamespace(k8s=k8s)))


class TestStart:
    async def test_submits_the_executor_job(
        self, service: SetupService, k8s: AsyncMock, seed_experiment: SeedExperiment
    ) -> None:
        exp_id, _ = await seed_experiment()
        experiment = _experiment(exp_id)

        run = await service.start(experiment, NB, None, gpu=False)

        assert run.state == SetupState.STARTING
        [manifest] = k8s.create_job_raw.call_args.args
        container = manifest["spec"]["template"]["spec"]["containers"][0]
        assert manifest["metadata"]["name"] == job_name(exp_id, NB)
        assert container["command"] == ["start.sh", "run-setup.sh"]
        assert container["args"] == [NB, "--status", status_path(NB)]
        assert container["workingDir"] == f"/mddash/{exp_id}"

    async def test_a_second_start_while_one_runs_conflicts(self, service: SetupService, k8s: AsyncMock) -> None:
        k8s.read_job.return_value = _job()

        with pytest.raises(ApiError) as exc:
            await service.start(_experiment("e1"), NB, None, gpu=False)

        assert exc.value.status_code == 409
        k8s.create_job_raw.assert_not_called()

    async def test_quota_refuses_before_submitting(self, service: SetupService, k8s: AsyncMock) -> None:
        k8s.check_quota_headroom.return_value = "CPU quota would be exceeded."

        with pytest.raises(Forbidden):
            await service.start(_experiment("e1"), NB, None, gpu=False)

        k8s.create_job_raw.assert_not_called()

    async def test_replaces_a_finished_job_and_its_old_doc(
        self, service: SetupService, k8s: AsyncMock, seed_experiment: SeedExperiment, tmp_path: Path
    ) -> None:
        exp_id, exp_dir = await seed_experiment()
        k8s.read_job.return_value = _job([SimpleNamespace(type="Complete", status="True")])
        (exp_dir / status_path(NB)).write_text(json.dumps({**RUNNING_DOC, "state": "done"}))

        await service.start(_experiment(exp_id), NB, None, gpu=False)

        k8s.delete_job_foreground.assert_awaited_once_with(job_name(exp_id, NB))
        assert not (exp_dir / status_path(NB)).exists()


class TestGetAndStop:
    async def test_an_image_pull_failure_reads_as_friendly_failed(
        self, service: SetupService, k8s: AsyncMock, seed_experiment: SeedExperiment
    ) -> None:
        exp_id, _ = await seed_experiment()
        k8s.read_job.return_value = _job()
        waiting = SimpleNamespace(reason="ImagePullBackOff")
        k8s.list_pods_by_label.return_value = [
            SimpleNamespace(
                status=SimpleNamespace(
                    conditions=[],
                    container_statuses=[
                        SimpleNamespace(state=SimpleNamespace(waiting=waiting, terminated=None), last_state=None)
                    ],
                )
            )
        ]

        run = await service.get(_experiment(exp_id), NB)

        assert run.state == SetupState.FAILED
        assert run.error is not None
        assert run.error.message == "The setup environment could not be downloaded."

    async def test_done_with_a_valid_manifest(
        self, service: SetupService, seed_experiment: SeedExperiment, db_session: object
    ) -> None:
        exp_id, exp_dir = await seed_experiment()
        write_simulation(exp_dir, "md.simulation.json")
        (exp_dir / status_path(NB)).write_text(
            json.dumps({**RUNNING_DOC, "state": "done", "manifests": ["md.simulation.json"]})
        )
        experiment = _experiment(exp_id)

        run = await service.get(experiment, NB)

        assert (run.state, run.manifests) == (SetupState.DONE, ["md.simulation.json"])

    async def test_stop_deletes_the_job_and_marks_the_doc(
        self, service: SetupService, k8s: AsyncMock, seed_experiment: SeedExperiment
    ) -> None:
        exp_id, exp_dir = await seed_experiment()
        k8s.read_job.return_value = _job()
        (exp_dir / status_path(NB)).write_text(json.dumps(RUNNING_DOC))

        await service.stop(_experiment(exp_id), NB)

        k8s.delete_job_foreground.assert_awaited_once_with(job_name(exp_id, NB))
        doc = json.loads((exp_dir / status_path(NB)).read_text())
        assert (doc["state"], doc["step"], doc["title"]) == ("stopped", 4, "Solvate")


class TestRoutes:
    async def test_never_ran_is_404(self, client: AsyncClient, seed_experiment: SeedExperiment) -> None:
        exp_id, exp_dir = await seed_experiment()
        (exp_dir / NB).write_text("{}")

        with patch("clients.k8s.K8sClient.read_job", AsyncMock(return_value=None)):
            response = await client.get(f"/dash/api/experiments/{exp_id}/setup")

        assert response.status_code == 404

    async def test_a_missing_notebook_is_404(self, client: AsyncClient, seed_experiment: SeedExperiment) -> None:
        exp_id, _ = await seed_experiment()

        response = await client.post(f"/dash/api/experiments/{exp_id}/setup", json={})

        assert response.status_code == 404
