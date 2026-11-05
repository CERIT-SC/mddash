"""
Tests for mdrun-api Kubernetes job manifest construction.

Verifies that simulations run in the directory of their primary input file
(the TPR for GROMACS, the mdin for AMBER) and that the S3 sync back to object
storage is scoped to that simulation directory instead of the whole experiment.
"""

import subprocess
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import k8s_client
import pytest
from enums import JobStatus
from k8s_client import MeasuredUsage
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
        assert "trap 'mddash_usage_final || true; touch /data/job_completed' EXIT" in command

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
        assert "trap 'mddash_usage_final || true; touch /data/job_completed' EXIT" in command

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


class TestGpuNodeSelector:
    """GPU jobs pin to the configured GPU product; CPU jobs schedule anywhere."""

    def _create_gmx(self, mocker: MockerFixture, *, gpu_product: str, nb: str, pme: str) -> dict[str, Any]:
        mocker.patch.object(k8s_client, "GPU_TYPE", "nvidia.com/gpu")
        mocker.patch.object(k8s_client, "GPU_PRODUCT", gpu_product)
        batch_v1 = _create(mocker)
        k8s_client.create_gromacs_job(
            ns="ns",
            bucket_name="bucket",
            name="mdrun-job",
            experiment_id="exp123",
            deffnm="md",
            np=1,
            ntomp=2,
            nb=nb,
            pme=pme,
            extra_args="",
        )
        return _manifest(batch_v1)

    def test_gpu_job_pins_to_configured_gpu_product(self, mocker: MockerFixture) -> None:
        pod_spec = self._create_gmx(mocker, gpu_product="NVIDIA-A40", nb="gpu", pme="cpu")["spec"]["template"]["spec"]
        assert pod_spec["nodeSelector"] == {"nvidia.com/gpu.product": "NVIDIA-A40"}

    def test_cpu_job_has_no_node_selector(self, mocker: MockerFixture) -> None:
        pod_spec = self._create_gmx(mocker, gpu_product="NVIDIA-A40", nb="cpu", pme="cpu")["spec"]["template"]["spec"]
        assert "nodeSelector" not in pod_spec

    def test_gpu_job_without_configured_product_has_no_node_selector(self, mocker: MockerFixture) -> None:
        pod_spec = self._create_gmx(mocker, gpu_product="", nb="gpu", pme="cpu")["spec"]["template"]["spec"]
        assert "nodeSelector" not in pod_spec


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


class TestSimulationResources:
    """Requests equal limits; the ledger records the same numbers."""

    def test_gpu_gromacs_job_requests(self, mocker: MockerFixture) -> None:
        mocker.patch.object(k8s_client, "GPU_TYPE", "nvidia.com/gpu")
        batch_v1 = _create(mocker)

        k8s_client.create_gromacs_job(
            ns="ns",
            bucket_name="bucket",
            name="mdrun-job",
            experiment_id="exp123",
            deffnm="md",
            np=2,
            ntomp=8,
            nb="gpu",
            pme="cpu",
            extra_args="",
        )

        quantities = {"cpu": "16", "memory": "8Gi", "nvidia.com/gpu": "1"}
        resources = _manifest(batch_v1)["spec"]["template"]["spec"]["containers"][0]["resources"]
        assert resources == {"requests": quantities, "limits": quantities}

    def test_mpi_amber_job_requests(self, mocker: MockerFixture) -> None:
        mocker.patch.object(k8s_client, "GPU_TYPE", "nvidia.com/gpu")
        batch_v1 = _create(mocker)

        k8s_client.create_amber_job(
            ns="ns",
            bucket_name="bucket",
            name="mdrun-job",
            experiment_id="exp123",
            prmtop_name="sys.prmtop",
            inpcrd_name="sys.rst7",
            mdin_name="prod.in",
            binary="pmemd.MPI",
            np=4,
            ntomp=2,
            ewald="default",
            extra_args="",
        )

        quantities = {"cpu": "8", "memory": "16Gi", "nvidia.com/gpu": "0"}
        resources = _manifest(batch_v1)["spec"]["template"]["spec"]["containers"][0]["resources"]
        assert resources == {"requests": quantities, "limits": quantities}


class TestOwnerMetadata:
    """Job and pod carry the owner so operators can see whose pods hold resources."""

    def test_owner_labels_the_job_and_its_pod(self, mocker: MockerFixture) -> None:
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
            owner="alice@example.org",
            owner_namespace="mddash-user-alice-ns",
        )

        manifest = _manifest(batch_v1)
        job_meta, pod_meta = manifest["metadata"], manifest["spec"]["template"]["metadata"]
        owner_labels = {
            "mddash.io/workload": "mdrun",
            "mddash.io/engine": "gmx",
            "mddash.io/user-namespace": "mddash-user-alice-ns",
        }
        assert job_meta["labels"] == {"app": "mdrun-job", **owner_labels}
        assert pod_meta["labels"] == {"job": "mdrun-job", **owner_labels}
        assert job_meta["annotations"] == pod_meta["annotations"] == {"mddash.io/user": "alice@example.org"}

    def test_unattributed_job_has_no_user_metadata(self, mocker: MockerFixture) -> None:
        batch_v1 = _create(mocker)

        k8s_client.create_amber_job(
            ns="ns",
            bucket_name="bucket",
            name="mdrun-job",
            experiment_id="exp123",
            prmtop_name="sys.prmtop",
            inpcrd_name="sys.rst7",
            mdin_name="prod.in",
            binary="pmemd.cuda",
            np=1,
            ntomp=4,
            ewald="default",
            extra_args="",
        )

        pod_meta = _manifest(batch_v1)["spec"]["template"]["metadata"]
        assert pod_meta["labels"] == {"job": "mdrun-job", "mddash.io/workload": "mdrun", "mddash.io/engine": "amber"}
        assert "annotations" not in pod_meta


POD_START = datetime(2026, 10, 1, 8, 0, tzinfo=UTC)


def _pod(*finished_at: datetime | None) -> MagicMock:
    pod = MagicMock()
    pod.status.start_time = POD_START
    statuses = []
    for finished in finished_at:
        container = MagicMock()
        container.state.terminated = None if finished is None else MagicMock(finished_at=finished)
        statuses.append(container)
    pod.status.container_statuses = statuses
    return pod


class TestGetPodTimes:
    """The allocation window is the pod's start until its last container exits."""

    def test_window_ends_when_the_last_container_exits(self, mocker: MockerFixture) -> None:
        core_v1 = mocker.patch.object(k8s_client, "core_v1")
        sim_end = datetime(2026, 10, 1, 10, 0, tzinfo=UTC)
        sync_end = datetime(2026, 10, 1, 10, 1, tzinfo=UTC)
        core_v1.list_namespaced_pod.return_value = MagicMock(items=[_pod(sim_end, sync_end)])

        assert k8s_client.get_pod_times(ns="ns", name="mdrun-job") == (POD_START, sync_end)
        assert core_v1.list_namespaced_pod.call_args.kwargs["label_selector"] == "job-name=mdrun-job"

    def test_window_stays_open_while_a_container_runs(self, mocker: MockerFixture) -> None:
        core_v1 = mocker.patch.object(k8s_client, "core_v1")
        core_v1.list_namespaced_pod.return_value = MagicMock(items=[_pod(datetime(2026, 10, 1, 10, tzinfo=UTC), None)])

        assert k8s_client.get_pod_times(ns="ns", name="mdrun-job") == (POD_START, None)

    def test_missing_pod_has_no_times(self, mocker: MockerFixture) -> None:
        core_v1 = mocker.patch.object(k8s_client, "core_v1")
        core_v1.list_namespaced_pod.return_value = MagicMock(items=[])

        assert k8s_client.get_pod_times(ns="ns", name="mdrun-job") == (None, None)

    def test_api_error_has_no_times(self, mocker: MockerFixture) -> None:
        core_v1 = mocker.patch.object(k8s_client, "core_v1")
        core_v1.list_namespaced_pod.side_effect = ApiException(status=500)

        assert k8s_client.get_pod_times(ns="ns", name="mdrun-job") == (None, None)


CPU_STAT = (
    "usage_usec 7200000000\nuser_usec 7000000000\nsystem_usec 200000000\n"
    "nr_periods 100\nnr_throttled 3\nthrottled_usec 90000000\n"
)
FOUR_GIB = 4 * 2**30
TWO_GIB = 2 * 2**30
CONTAINER_START = datetime(2026, 11, 5, 8, 0, tzinfo=UTC)


def _pressure(total_usec: int) -> str:
    return (
        f"some avg10=0.00 avg60=0.00 avg300=0.00 total={total_usec}\nfull avg10=0.00 avg60=0.00 avg300=0.00 total=0\n"
    )


@pytest.fixture
def cgroup(tmp_path: Path) -> Path:
    """Write the container's own cgroup v2 counters, which ``CPU_JOB_USAGE`` reads back."""
    directory = tmp_path / "cgroup"
    directory.mkdir()
    (directory / "cpu.stat").write_text(CPU_STAT)
    (directory / "memory.peak").write_text(f"{FOUR_GIB}\n")
    (directory / "memory.events").write_text("low 0\nhigh 0\nmax 2\noom 1\noom_kill 1\noom_group_kill 0\n")
    (directory / "cpu.pressure").write_text(_pressure(1_800_000_000))
    (directory / "memory.pressure").write_text(_pressure(5_000_000))
    (directory / "io.pressure").write_text(_pressure(30_000_000))
    (directory / "io.stat").write_text(
        f"259:0 rbytes={2**30} wbytes={TWO_GIB} rios=1 wios=2 dbytes=0 dios=0\n"
        f"8:0 rbytes={2**30} wbytes=0 rios=1 wios=0 dbytes=0 dios=0\n"
    )
    return directory


def _fake_nvidia_smi(tmp_path: Path, sample: str) -> Path:
    """Put an ``nvidia-smi`` on PATH that prints ``sample`` for one GPU and records each call."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    fake = bin_dir / "nvidia-smi"
    fake.write_text(f"#!/bin/sh\necho called >> {tmp_path / 'nvidia-smi.calls'}\necho '{sample}'\n")
    fake.chmod(0o755)
    return bin_dir


@pytest.fixture
def nvidia_smi(tmp_path: Path) -> Path:
    """One GPU at 60 % with 2 GiB used, drawing 150.5 W."""
    return _fake_nvidia_smi(tmp_path, "60, 2048, 150.5")


def _run(script: str, path: Path | None = None, cwd: Path | None = None) -> list[str]:
    """Run a job script the way the container does and return its log lines."""
    env = {"PATH": f"{path}:/usr/bin:/bin" if path else "/usr/bin:/bin"}
    result = subprocess.run(
        ["bash", "-c", f"set -euo pipefail\n{script}"],
        capture_output=True,
        text=True,
        env=env,
        cwd=cwd,
        timeout=30,
        check=False,
    )
    return result.stdout.splitlines()


def _last_usage(lines: list[str]) -> MeasuredUsage | None:
    return next((usage for line in reversed(lines) if (usage := k8s_client.parse_usage_line(line))), None)


def _untimed(usage: MeasuredUsage | None) -> MeasuredUsage:
    """Drop the container's clock readings, which differ on every run."""
    assert usage is not None
    assert usage.container_started_at is not None
    assert usage.measured_at is not None
    assert usage.measured_at >= usage.container_started_at
    return replace(usage, container_started_at=None, measured_at=None)


CPU_JOB_USAGE = MeasuredUsage(
    cpu_core_seconds=7200.0,
    memory_peak_gib=4.0,
    gpu_utilization=None,
    gpu_memory_peak_gib=None,
    complete=True,
    cpu_throttled_seconds=90.0,
    cpu_stall_seconds=1800.0,
    memory_stall_seconds=5.0,
    io_stall_seconds=30.0,
    oom_kills=1,
    io_read_bytes=TWO_GIB,
    io_write_bytes=TWO_GIB,
)


class TestUsageMeasurement:
    """The simulation container measures itself and logs the result for MDRun to read."""

    def test_cpu_job_reports_its_cgroup_counters(self, cgroup: Path) -> None:
        block = k8s_client._usage_block(gpus=False, cgroup=str(cgroup), interval=3600)

        lines = _run(f"{block}\nmddash_usage_final")

        assert _untimed(_last_usage(lines)) == CPU_JOB_USAGE

    def test_gpu_job_averages_nvidia_smi_samples(self, cgroup: Path, nvidia_smi: Path) -> None:
        block = k8s_client._usage_block(gpus=True, cgroup=str(cgroup), interval=0.1)

        lines = _run(f"{block}\nsleep 1\nmddash_usage_final", path=nvidia_smi)

        assert _untimed(_last_usage(lines)) == replace(
            CPU_JOB_USAGE, gpu_utilization=60.0, gpu_memory_peak_gib=2.0, gpu_power_watts=150.5
        )
        # Periodic lines cover a stop, which deletes the pod before the exit line.
        assert any(usage and not usage.complete for usage in map(k8s_client.parse_usage_line, lines))

    def test_gpu_without_a_power_reading_still_reports_utilization(self, cgroup: Path, tmp_path: Path) -> None:
        block = k8s_client._usage_block(gpus=True, cgroup=str(cgroup), interval=0.1)

        lines = _run(f"{block}\nsleep 0.5\nmddash_usage_final", path=_fake_nvidia_smi(tmp_path, "60, 2048, [N/A]"))

        usage = _last_usage(lines)
        assert usage is not None
        assert (usage.gpu_utilization, usage.gpu_power_watts) == (60.0, None)

    @pytest.mark.parametrize(
        ("performance", "log_name", "log"),
        [
            # mdrun -cpi appends each part's report to the same log; the last one is this run's.
            (
                k8s_client._gromacs_performance,
                "md.log",
                "               (ns/day)    (hour/ns)\nPerformance:       10.000        2.400\n"
                "               (ns/day)    (hour/ns)\nPerformance:       12.500        1.920\n",
            ),
            # pmemd reports the last steps, then all steps.
            (
                k8s_client._amber_performance,
                "prod.out",
                "|         ns/day =     146.21   seconds/ns =     590.93\n"
                "|     Average timings for all steps:\n"
                "|         ns/day =      12.50   seconds/ns =    6912.00\n",
            ),
        ],
        ids=["gromacs", "amber"],
    )
    def test_exit_line_reports_the_engines_speed(
        self, cgroup: Path, tmp_path: Path, performance: Any, log_name: str, log: str
    ) -> None:
        (tmp_path / log_name).write_text(log)
        block = k8s_client._usage_block(
            gpus=False, cgroup=str(cgroup), interval=3600, performance=performance(log_name)
        )

        lines = _run(f"{block}\nmddash_usage_final", cwd=tmp_path)

        usage = _last_usage(lines)
        assert usage is not None
        assert usage.ns_per_day == pytest.approx(12.5)

    def test_missing_engine_report_leaves_the_measurement(self, cgroup: Path, tmp_path: Path) -> None:
        block = k8s_client._usage_block(
            gpus=False, cgroup=str(cgroup), interval=3600, performance=k8s_client._gromacs_performance("md.log")
        )

        lines = _run(f"{block}\nmddash_usage_final", cwd=tmp_path)

        assert _untimed(_last_usage(lines)) == CPU_JOB_USAGE

    def test_cpu_job_never_samples_gpus(self, cgroup: Path, nvidia_smi: Path, tmp_path: Path) -> None:
        """A CPU job on a GPU node may see other jobs' GPUs."""
        block = k8s_client._usage_block(gpus=False, cgroup=str(cgroup), interval=0.1)

        _run(f"{block}\nsleep 0.5\nmddash_usage_final", path=nvidia_smi)

        assert not (tmp_path / "nvidia-smi.calls").exists()

    def test_exit_trap_reports_after_the_simulation_ends(self, cgroup: Path) -> None:
        block = k8s_client._usage_block(gpus=False, cgroup=str(cgroup), interval=3600)
        guard = k8s_client._sim_guard_block("sleep")

        lines = _run(f"{block}\nsleep 0.2 &\n{guard}")

        assert lines[-2] == "Simulation completed."
        usage = k8s_client.parse_usage_line(lines[-1])
        assert usage is not None
        assert usage.complete

    def test_unreadable_counters_leave_the_simulation_running(self, tmp_path: Path) -> None:
        block = k8s_client._usage_block(gpus=True, cgroup=str(tmp_path / "missing"), interval=3600)

        lines = _run(f"{block}\necho simulation-ran\nmddash_usage_final")

        assert "simulation-ran" in lines
        assert _last_usage(lines) is None


def _usage_log(*lines: str) -> MagicMock:
    core_v1 = MagicMock()
    pod = MagicMock()
    pod.metadata.name = "mdrun-job-abcde"
    core_v1.list_namespaced_pod.return_value = MagicMock(items=[pod])
    body = "\n".join(lines).encode()

    def read_log(**kwargs: Any) -> object:
        # kubernetes 36 returns a preloaded text/plain body as the repr of its bytes: "b'...\\n...'".
        return MagicMock(data=body) if kwargs.get("_preload_content") is False else str(body)

    core_v1.read_namespaced_pod_log.side_effect = read_log
    return core_v1


class TestGetMeasuredUsage:
    """MDRun reads the latest measurement from the simulation container's log."""

    def test_latest_line_wins(self, mocker: MockerFixture) -> None:
        core_v1 = mocker.patch.object(
            k8s_client,
            "core_v1",
            _usage_log(
                "mddash-usage final=0 cpu_usec=1000000 memory_peak_bytes=1073741824",
                "step 5000, remaining wall clock time: 0 s",
                "Simulation completed.",
                "mddash-usage final=1 cpu_usec=3000000 memory_peak_bytes=2147483648",
            ),
        )

        assert k8s_client.get_measured_usage(ns="ns", name="mdrun-job") == MeasuredUsage(
            cpu_core_seconds=3.0,
            memory_peak_gib=2.0,
            gpu_utilization=None,
            gpu_memory_peak_gib=None,
            complete=True,
        )
        kwargs = core_v1.read_namespaced_pod_log.call_args.kwargs
        assert (kwargs["name"], kwargs["container"]) == ("mdrun-job-abcde", "mdrun-job")

    def test_log_without_a_measurement(self, mocker: MockerFixture) -> None:
        mocker.patch.object(k8s_client, "core_v1", _usage_log("Simulation completed."))

        assert k8s_client.get_measured_usage(ns="ns", name="mdrun-job") is None

    def test_missing_pod(self, mocker: MockerFixture) -> None:
        core_v1 = mocker.patch.object(k8s_client, "core_v1")
        core_v1.list_namespaced_pod.return_value = MagicMock(items=[])

        assert k8s_client.get_measured_usage(ns="ns", name="mdrun-job") is None

    def test_empty_log(self, mocker: MockerFixture) -> None:
        mocker.patch.object(k8s_client, "core_v1", _usage_log())

        assert k8s_client.get_measured_usage(ns="ns", name="mdrun-job") is None

    def test_unreadable_log(self, mocker: MockerFixture) -> None:
        core_v1 = mocker.patch.object(k8s_client, "core_v1", _usage_log())
        core_v1.read_namespaced_pod_log.side_effect = ApiException(status=500)

        assert k8s_client.get_measured_usage(ns="ns", name="mdrun-job") is None


@pytest.mark.parametrize(
    ("line", "expected"),
    [
        ("mddash-usage final=0 cpu_usec= memory_peak_bytes=", None),
        (
            "mddash-usage final=0 cpu_usec=1500000 memory_peak_bytes=",
            MeasuredUsage(
                cpu_core_seconds=1.5,
                memory_peak_gib=None,
                gpu_utilization=None,
                gpu_memory_peak_gib=None,
                complete=False,
            ),
        ),
        ("mddash-usage final=1 cpu_usec=lots memory_peak_bytes=", None),
        ("simulation output mentioning mddash-usage final=1 cpu_usec=1", None),
        (
            "mddash-usage final=1 cpu_usec=1500000 ns_per_day=nan started=99999999999999999999",
            MeasuredUsage(
                cpu_core_seconds=1.5,
                memory_peak_gib=None,
                gpu_utilization=None,
                gpu_memory_peak_gib=None,
                complete=True,
            ),
        ),
        (
            f"mddash-usage final=0 started={int(CONTAINER_START.timestamp())} "
            f"at={int(CONTAINER_START.timestamp()) + 3600} cpu_usec=1000000 oom_kills=0 cpu_stall_usec=2000000 "
            "gpu_samples=2 gpu_util_sum=100 gpu_memory_peak_mib=1024 gpu_power_sum_w=300.0 gpu_power_samples=2",
            MeasuredUsage(
                cpu_core_seconds=1.0,
                memory_peak_gib=None,
                gpu_utilization=50.0,
                gpu_memory_peak_gib=1.0,
                complete=False,
                container_started_at=CONTAINER_START,
                measured_at=CONTAINER_START + timedelta(hours=1),
                cpu_stall_seconds=2.0,
                oom_kills=0,
                gpu_power_watts=150.0,
            ),
        ),
    ],
    ids=["empty", "cpu-only", "not-a-number", "not-at-line-start", "not-finite", "diagnostics"],
)
def test_parse_usage_line_takes_only_complete_numbers(line: str, expected: MeasuredUsage | None) -> None:
    assert k8s_client.parse_usage_line(line) == expected


@pytest.mark.parametrize(
    "create",
    [
        lambda: k8s_client.create_gromacs_job(
            "ns", "bucket", "mdrun-job", "exp", "md", 2, 4, nb="gpu", pme="cpu", extra_args="-maxh 1"
        ),
        lambda: k8s_client.create_gromacs_job("ns", "bucket", "mdrun-job", "exp", "md", 2, 4, "cpu", "cpu", ""),
        lambda: k8s_client.create_amber_job(
            "ns", "bucket", "mdrun-job", "exp", "s.prmtop", "s.rst7", "md.mdin", "pmemd.cuda", 1, 4, "default", ""
        ),
        lambda: k8s_client.create_amber_job(
            "ns", "bucket", "mdrun-job", "exp", "s.prmtop", "s.rst7", "md.mdin", "pmemd.MPI", 2, 2, "optimized", ""
        ),
    ],
    ids=["gmx-gpu", "gmx-cpu", "amber-cuda", "amber-mpi"],
)
def test_job_command_is_valid_bash(mocker: MockerFixture, create: Any) -> None:
    batch_v1 = _create(mocker)
    create()

    result = subprocess.run(["bash", "-n", "-c", _sim_command(_manifest(batch_v1))], capture_output=True, check=False)

    assert result.returncode == 0, result.stderr
