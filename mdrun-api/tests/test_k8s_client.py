"""
Tests for mdrun-api Kubernetes job manifest construction.

Verifies that simulations run in the directory of their primary input file
(the TPR for GROMACS, the mdin for AMBER) and that the S3 sync back to object
storage is scoped to that simulation directory instead of the whole experiment.
"""

from typing import Any
from unittest.mock import MagicMock

import k8s_client
from enums import JobStatus
from kubernetes.client.rest import ApiException
from pytest_mock import MockerFixture


def _sim_command(manifest: dict[str, Any]) -> str:
    return manifest["spec"]["template"]["spec"]["containers"][0]["command"][2]


def _s3_init_command(manifest: dict[str, Any]) -> str:
    return manifest["spec"]["template"]["spec"]["initContainers"][0]["command"][2]


def _s3_sync_command(manifest: dict[str, Any]) -> str:
    return manifest["spec"]["template"]["spec"]["containers"][1]["command"][2]


def _working_dir(manifest: dict[str, Any]) -> str:
    return manifest["spec"]["template"]["spec"]["containers"][0]["workingDir"]


def _create(mocker: MockerFixture) -> MagicMock:
    batch_v1 = mocker.patch.object(k8s_client, "batch_v1")
    mocker.patch("k8s_client.ping_resource", return_value=False)
    return batch_v1


def _manifest(batch_v1: MagicMock) -> dict[str, Any]:
    return batch_v1.create_namespaced_job.call_args.kwargs["body"]


class TestGromacsManifest:
    """GROMACS jobs run in the TPR directory."""

    def test_nested_tpr_runs_in_tpr_directory(self, mocker: MockerFixture) -> None:
        """A nested TPR runs in its own directory and uses a basename deffnm."""
        batch_v1 = _create(mocker)

        # deffnm is the TPR path without .tpr (experiment-relative)
        k8s_client.create_gromacs_job(
            ns="ns",
            bucket_name="bucket",
            name="mdrun-job",
            experiment_id="exp123",
            deffnm="production/md",
            np=2,
            ntomp=4,
            nb="gpu",
            pme="gpu",
            extra_args="",
        )

        manifest = _manifest(batch_v1)

        assert _working_dir(manifest) == "/data/exp123/production"
        # deffnm is the basename only (relative to the working directory)
        assert "-deffnm md" in _sim_command(manifest)
        assert "-deffnm production/md" not in _sim_command(manifest)
        # stdout/stderr logs are written into the working directory
        assert "mdrun-job.out" in _sim_command(manifest)

    def test_nested_tpr_scopes_sync_to_simulation_directory(self, mocker: MockerFixture) -> None:
        """S3 download stays whole-experiment; upload is scoped to the sim dir."""
        batch_v1 = _create(mocker)

        k8s_client.create_gromacs_job(
            ns="ns",
            bucket_name="bucket",
            name="mdrun-job",
            experiment_id="exp123",
            deffnm="production/md",
            np=2,
            ntomp=4,
            nb="gpu",
            pme="gpu",
            extra_args="",
        )

        manifest = _manifest(batch_v1)

        init = _s3_init_command(manifest)
        sync = _s3_sync_command(manifest)

        # Init downloads the whole experiment into the experiment directory.
        assert "s3remote:bucket/exp123/" in init
        assert "/data/exp123/" in init

        # Sync uploads only the simulation directory back to S3.
        assert "s3remote:bucket/exp123/production/" in sync
        assert "/data/exp123/production/" in sync

    def test_root_tpr_runs_in_experiment_root(self, mocker: MockerFixture) -> None:
        """A root-level TPR runs in the experiment root (whole experiment sync)."""
        batch_v1 = _create(mocker)

        k8s_client.create_gromacs_job(
            ns="ns",
            bucket_name="bucket",
            name="mdrun-job",
            experiment_id="exp123",
            deffnm="md",
            np=1,
            ntomp=2,
            nb="cpu",
            pme="cpu",
            extra_args="",
        )

        manifest = _manifest(batch_v1)

        assert _working_dir(manifest) == "/data/exp123"
        assert "-deffnm md" in _sim_command(manifest)
        # Root simulation dir means the whole experiment is synced back.
        sync = _s3_sync_command(manifest)
        assert "s3remote:bucket/exp123/" in sync
        assert "exp123/production" not in sync


class TestSimGuardAndSyncTraps:
    """Commands survive pod deletion: TERM reaches the workload and the sidecar does a final copy."""

    def test_gmx_sim_command_signals_mdrun_by_name_and_always_marks_completion(self, mocker: MockerFixture) -> None:
        batch_v1 = _create(mocker)
        k8s_client.create_gromacs_job(
            ns="ns",
            bucket_name="bucket",
            name="mdrun-job",
            experiment_id="exp123",
            deffnm="production/md",
            np=2,
            ntomp=4,
            nb="gpu",
            pme="gpu",
            extra_args="",
        )
        command = _sim_command(_manifest(batch_v1))

        assert "MD_PID=$!" in command
        assert "trap on_term TERM INT" in command
        # TERM must hit mdrun itself: orterun kills ranks on TERM before they checkpoint.
        assert "pkill -TERM -x 'gmx'" in command
        # Launcher TERM is only the fallback when no sim process matched.
        assert 'kill -TERM "$MD_PID"' in command
        assert "trap 'touch /data/job_completed' EXIT" in command

    def test_amber_sim_command_uses_sim_guard(self, mocker: MockerFixture) -> None:
        batch_v1 = _create(mocker)
        k8s_client.create_amber_job(
            ns="ns",
            bucket_name="bucket",
            name="mdrun-job",
            experiment_id="exp123",
            prmtop_name="villin.prmtop",
            inpcrd_name="villin.rst7",
            mdin_name="prod.mdin",
            binary="pmemd.cuda",
            np=1,
            ntomp=4,
            ewald="default",
            extra_args="",
        )
        command = _sim_command(_manifest(batch_v1))

        assert "MD_PID=$!" in command
        assert "trap on_term TERM INT" in command
        assert "pkill -TERM -x 'pmemd\\.cuda'" in command
        assert "trap 'touch /data/job_completed' EXIT" in command

    def test_amber_mpi_sim_command_signals_pmemd_by_name(self, mocker: MockerFixture) -> None:
        batch_v1 = _create(mocker)
        k8s_client.create_amber_job(
            ns="ns",
            bucket_name="bucket",
            name="mdrun-job",
            experiment_id="exp123",
            prmtop_name="villin.prmtop",
            inpcrd_name="villin.rst7",
            mdin_name="prod.mdin",
            binary="pmemd.mpi",
            np=2,
            ntomp=2,
            ewald="default",
            extra_args="",
        )
        command = _sim_command(_manifest(batch_v1))

        assert "mpirun" in command
        assert "pkill -TERM -x 'pmemd\\.MPI'" in command

    def test_s3_sync_traps_term_and_waits_for_completion_marker(self, mocker: MockerFixture) -> None:
        batch_v1 = _create(mocker)
        k8s_client.create_gromacs_job(
            ns="ns",
            bucket_name="bucket",
            name="mdrun-job",
            experiment_id="exp123",
            deffnm="production/md",
            np=2,
            ntomp=4,
            nb="gpu",
            pme="gpu",
            extra_args="",
        )
        sync = _s3_sync_command(_manifest(batch_v1))

        assert "trap on_term TERM INT" in sync
        # Bounded wait for the sim's completion marker, then a final checksummed copy.
        assert "[ ! -f /data/job_completed ]" in sync
        assert "--checksum" in sync


class TestDeleteJobGrace:
    """The pod grace period is parameterizable so stops can outlive plain deletes."""

    def _delete(self, mocker: MockerFixture, **kwargs: Any) -> MagicMock:
        batch_v1 = mocker.patch.object(k8s_client, "batch_v1")
        mocker.patch("k8s_client.ping_resource", return_value=True)
        k8s_client.delete_job(ns="ns", name="mdrun-job", **kwargs)
        return batch_v1

    def test_default_grace_period(self, mocker: MockerFixture) -> None:
        batch_v1 = self._delete(mocker)
        body = batch_v1.delete_namespaced_job.call_args.kwargs["body"]
        assert body.grace_period_seconds == 5

    def test_custom_grace_period(self, mocker: MockerFixture) -> None:
        batch_v1 = self._delete(mocker, grace_period_seconds=k8s_client.STOP_GRACE_PERIOD_SECONDS)
        body = batch_v1.delete_namespaced_job.call_args.kwargs["body"]
        assert body.grace_period_seconds == k8s_client.STOP_GRACE_PERIOD_SECONDS


class TestAmberManifest:
    """AMBER jobs run in the mdin directory with relative input references."""

    def test_nested_mdin_uses_relative_input_paths(self, mocker: MockerFixture) -> None:
        """Inputs outside the mdin directory are referenced via relative paths."""
        batch_v1 = _create(mocker)

        k8s_client.create_amber_job(
            ns="ns",
            bucket_name="bucket",
            name="mdrun-job",
            experiment_id="exp123",
            prmtop_name="villin.prmtop",
            inpcrd_name="villin.rst7",
            mdin_name="sub/prod.mdin",
            binary="pmemd.cuda",
            np=1,
            ntomp=4,
            ewald="default",
            extra_args="",
        )

        manifest = _manifest(batch_v1)
        command = _sim_command(manifest)

        assert _working_dir(manifest) == "/data/exp123/sub"
        # mdin is referenced by basename (relative to the working directory).
        assert "-i prod.mdin" in command
        assert "-i sub/prod.mdin" not in command
        # prmtop/inpcrd outside the mdin dir are referenced via parent paths.
        assert "-p ../villin.prmtop" in command
        assert "-c ../villin.rst7" in command
        # Outputs use the mdin stem and land in the working directory.
        assert "-o prod.out" in command
        assert "-x prod.nc" in command
        # stdout/stderr logs are written into the working directory.
        assert "mdrun-job.out" in command

    def test_nested_mdin_scopes_sync_to_simulation_directory(self, mocker: MockerFixture) -> None:
        """S3 upload is scoped to the mdin directory."""
        batch_v1 = _create(mocker)

        k8s_client.create_amber_job(
            ns="ns",
            bucket_name="bucket",
            name="mdrun-job",
            experiment_id="exp123",
            prmtop_name="villin.prmtop",
            inpcrd_name="villin.rst7",
            mdin_name="sub/prod.mdin",
            binary="pmemd.cuda",
            np=1,
            ntomp=4,
            ewald="default",
            extra_args="",
        )

        manifest = _manifest(batch_v1)

        assert "s3remote:bucket/exp123/sub/" in _s3_sync_command(manifest)
        assert "/data/exp123/sub/" in _s3_sync_command(manifest)
        # Init still downloads the whole experiment.
        assert "s3remote:bucket/exp123/" in _s3_init_command(manifest)

    def test_root_inputs_run_in_experiment_root(self, mocker: MockerFixture) -> None:
        """Root-level mdin/prmtop/inpcrd run in the experiment root."""
        batch_v1 = _create(mocker)

        k8s_client.create_amber_job(
            ns="ns",
            bucket_name="bucket",
            name="mdrun-job",
            experiment_id="exp123",
            prmtop_name="v.prmtop",
            inpcrd_name="v.rst7",
            mdin_name="prod.mdin",
            binary="pmemd.MPI",
            np=2,
            ntomp=1,
            ewald="optimized",
            extra_args="",
        )

        manifest = _manifest(batch_v1)
        command = _sim_command(manifest)

        assert _working_dir(manifest) == "/data/exp123"
        assert "-i prod.mdin" in command
        assert "-p v.prmtop" in command
        assert "-c v.rst7" in command
        sync = _s3_sync_command(manifest)
        assert "s3remote:bucket/exp123/" in sync
        assert "exp123/sub" not in sync


def _stub_status(
    mocker: MockerFixture,
    *,
    conditions: list[MagicMock] | None = None,
    active: int | None = 1,
    succeeded: int | None = None,
    failed: int | None = None,
    pod_phase: str | None = "Running",
    pod_error: Exception | None = None,
) -> MagicMock:
    """Patch the K8s clients for one get_job_status call; returns the core_v1 mock."""
    batch_v1 = mocker.patch.object(k8s_client, "batch_v1")
    core_v1 = mocker.patch.object(k8s_client, "core_v1")

    job = MagicMock()
    job.status.conditions = conditions
    job.status.active = active
    job.status.succeeded = succeeded
    job.status.failed = failed
    batch_v1.read_namespaced_job.return_value = job

    if pod_error is not None:
        core_v1.list_namespaced_pod.side_effect = pod_error
    else:
        pod = MagicMock()
        pod.status.phase = pod_phase
        core_v1.list_namespaced_pod.return_value = MagicMock(items=[pod])
    return core_v1


class TestGetJobStatus:
    """Pod-phase translation for jobs the controller hasn't stamped yet."""

    def test_succeeded_pod_reports_finished(self, mocker: MockerFixture) -> None:
        """A Succeeded pod is FINISHED even before the Job object is stamped Complete."""
        _stub_status(mocker, pod_phase="Succeeded")

        assert k8s_client.get_job_status(ns="ns", name="mdrun-job") is JobStatus.FINISHED

    def test_failed_pod_reports_error(self, mocker: MockerFixture) -> None:
        """A Failed pod is ERROR, not PENDING (backoffLimit 0 makes the phase terminal)."""
        _stub_status(mocker, pod_phase="Failed")

        assert k8s_client.get_job_status(ns="ns", name="mdrun-job") is JobStatus.ERROR

    def test_running_pod_reports_running(self, mocker: MockerFixture) -> None:
        """A Running pod keeps the job RUNNING."""
        _stub_status(mocker, pod_phase="Running")

        assert k8s_client.get_job_status(ns="ns", name="mdrun-job") is JobStatus.RUNNING

    def test_pre_start_pod_reports_pending(self, mocker: MockerFixture) -> None:
        """Pre-start phases (Pending, ContainerCreating) stay PENDING."""
        _stub_status(mocker, pod_phase="Pending")

        assert k8s_client.get_job_status(ns="ns", name="mdrun-job") is JobStatus.PENDING

    def test_job_conditions_short_circuit_the_pod_lookup(self, mocker: MockerFixture) -> None:
        """A stamped Complete condition answers without listing pods."""
        complete = MagicMock()
        complete.type = "Complete"
        complete.status = "True"
        core_v1 = _stub_status(mocker, conditions=[complete], pod_phase="Succeeded")

        assert k8s_client.get_job_status(ns="ns", name="mdrun-job") is JobStatus.FINISHED
        core_v1.list_namespaced_pod.assert_not_called()

    def test_phase_lookup_failure_falls_back_to_running(self, mocker: MockerFixture) -> None:
        """An active job whose pod phase can't be read stays RUNNING."""
        _stub_status(mocker, pod_error=ApiException(status=500))

        assert k8s_client.get_job_status(ns="ns", name="mdrun-job") is JobStatus.RUNNING
