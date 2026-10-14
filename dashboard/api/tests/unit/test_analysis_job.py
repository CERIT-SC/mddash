"""Unit tests for analysis job mwf command generation."""

from pathlib import Path
from unittest.mock import AsyncMock, PropertyMock, patch

import pytest
from config import ANALYSIS_RESOURCES
from enums import AnalysisType, DeviceType, Engine, JobStatus, PreprocessingMode
from errors import Forbidden
from models import Experiment, GromacsJob, Notebook
from models.analysis_job import (
    AnalysisJob,
    format_mwf_analysis_command,
    format_mwf_inputs_yaml,
    get_analysis_runtime_prep_commands,
    get_incomplete_task_dirs,
    get_runtime_prelude_commands,
)
from sqlalchemy.ext.asyncio import AsyncSession


class TestFormatMwfInputsYaml:
    """Tests for per-analysis mwf inputs generation."""

    def test_includes_auto_interactions_for_interaction_driven_analysis(self) -> None:
        """Hydrogen bond analysis should request automatic interaction processing."""
        content = format_mwf_inputs_yaml(AnalysisType.HBONDS)

        assert content == "name: mddash\ntype: trajectory\npbc_selection: auto\ninteractions:\n  - auto\n"

    def test_omits_auto_interactions_for_clusters(self) -> None:
        """Clusters should not force automatic interactions for the overall run."""
        content = format_mwf_inputs_yaml(AnalysisType.CLUSTERS)

        assert content == "name: mddash\ntype: trajectory\npbc_selection: auto\n"

    def test_sets_auto_pbc_selection(self) -> None:
        """pbc_selection must be 'auto' so mwf excludes solvent/ions/lipids from integrity checks."""
        content = format_mwf_inputs_yaml(AnalysisType.PCA)

        assert "pbc_selection: auto\n" in content
        assert "pbc_selection: none" not in content


class TestFormatMwfAnalysisCommand:
    """Tests for mwf shell command construction."""

    def test_incomplete_task_dirs_cover_project_relative_root(self) -> None:
        """Incomplete task directories are project-relative (MD dir is per-simulation)."""
        assert get_incomplete_task_dirs("inter") == [Path("incomplete_inter")]

    def test_runtime_prelude_sets_writable_home_and_git_safe_directory(self) -> None:
        """Third-party mwf jobs should get a writable HOME and a safe Git directory override."""
        commands = get_runtime_prelude_commands(AnalysisType.RMSDS)

        assert 'export HOME="$PWD/.mddash-home"' in commands
        assert 'mkdir -p "$HOME"' in commands
        assert "git config --global --add safe.directory /app/MDDB-workflow >/dev/null 2>&1 || true" in commands

    def test_clusters_command_does_not_inject_auto_interactions(self) -> None:
        """Clusters command should write an inputs file without interactions:auto."""
        command = format_mwf_analysis_command(
            analysis_name=AnalysisType.CLUSTERS,
            structure_file=Path("input.gro"),
            trajectory_file=Path("traj.xtc"),
            topology_file=None,
            preprocessing_mode=PreprocessingMode.AS_IS,
            simulation_path="protein.simulation.json",
        )

        assert "interactions:" not in command
        assert "mkdir -p incomplete_clusters" in command
        assert "-i clusters" in command

    def test_clusters_runtime_prep_covers_project_and_md_relative_temp_dirs(self) -> None:
        """Clusters prep should create temp screenshot directories for both path-resolution variants."""
        commands = get_analysis_runtime_prep_commands(AnalysisType.CLUSTERS)

        assert commands == ["mkdir -p incomplete_clusters"]

    def test_hbonds_runtime_prep_covers_project_and_md_relative_inter_dirs(self) -> None:
        """Interaction-driven analyses should create temp interaction directories for both path anchors."""
        commands = get_analysis_runtime_prep_commands(AnalysisType.HBONDS)

        assert commands == ["mkdir -p incomplete_inter"]

    def test_hbonds_command_injects_auto_interactions(self) -> None:
        """Hydrogen bond command should request automatic interactions."""
        command = format_mwf_analysis_command(
            analysis_name=AnalysisType.HBONDS,
            structure_file=Path("input.gro"),
            trajectory_file=Path("traj.xtc"),
            topology_file=None,
            preprocessing_mode=PreprocessingMode.AS_IS,
            simulation_path="protein.simulation.json",
        )

        assert "interactions:" in command
        assert "  - auto" in command
        assert "mkdir -p incomplete_inter" in command
        assert "-i hbonds" in command

    def test_topology_only_command_omits_structure_flag(self) -> None:
        """GMX analysis can derive structure from topology to avoid mismatched GRO/XTC atom sets."""
        command = format_mwf_analysis_command(
            analysis_name=AnalysisType.RMSDS,
            structure_file=None,
            trajectory_file=Path("traj.xtc"),
            topology_file=Path("topol.tpr"),
            preprocessing_mode=PreprocessingMode.AS_IS,
            simulation_path="protein.simulation.json",
        )

        assert "-stru" not in command
        assert "-top analysis/mwf/inputs/input_topology.tpr" in command


async def _experiment(db_session: AsyncSession, nsteps: int | None = None) -> Experiment:
    """Persist an experiment, reloaded with its job collections; optionally with a finished run."""
    db_session.add(Experiment(id="exptt", name="Analysis", engine=Engine.GMX))
    db_session.add(Notebook(experiment_id="exptt"))
    if nsteps is not None:
        db_session.add(
            GromacsJob(
                id="run-1",
                experiment_id="exptt",
                simulation_path="test.simulation.json",
                engine=Engine.GMX,
                np=1,
                ntomp=1,
                pme=DeviceType.CPU,
                nb=DeviceType.CPU,
                _nsteps=nsteps,
                _last_known_status=JobStatus.FINISHED,
            )
        )
    await db_session.commit()
    db_session.expunge_all()
    experiment = await db_session.get(Experiment, "exptt")
    assert experiment is not None
    return experiment


async def _start(db_session: AsyncSession, experiment: Experiment, tmp_path: Path) -> AnalysisJob:
    trajectory_file = tmp_path / "traj.xtc"
    trajectory_file.touch()
    topology_file = tmp_path / "topol.tpr"
    topology_file.touch()
    return await AnalysisJob.start(
        db_session,
        experiment=experiment,
        simulation_path="test.simulation.json",
        analysis_name=AnalysisType.RMSDS,
        structure_file=None,
        trajectory_file=trajectory_file,
        topology_file=topology_file,
        preprocessing_mode=PreprocessingMode.AS_IS,
    )


class TestAnalysisJobStartQuotaCheck:
    """Tests for the quota-headroom guard in AnalysisJob.start()."""

    async def test_raises_forbidden_when_quota_exceeded(self, db_session: AsyncSession, tmp_path: Path) -> None:
        """start() must raise Forbidden and not create a job when quota is insufficient."""
        experiment = await _experiment(db_session)
        with (
            patch("models.analysis_job.k8s.check_quota_headroom", AsyncMock(return_value="CPU quota exceeded")),
            patch("models.analysis_job.k8s.create_job") as mock_create_job,
            pytest.raises(Forbidden, match="CPU quota exceeded"),
        ):
            await _start(db_session, experiment, tmp_path)

        mock_create_job.assert_not_called()

    async def test_creates_job_with_analysis_resources_when_headroom_sufficient(
        self, db_session: AsyncSession, tmp_path: Path
    ) -> None:
        """start() must pass ANALYSIS_RESOURCES to create_job when quota has headroom."""
        experiment = await _experiment(db_session)
        with (
            patch("models.analysis_job.k8s.check_quota_headroom", AsyncMock(return_value=None)),
            patch("models.analysis_job.k8s.create_job") as mock_create_job,
        ):
            job = await _start(db_session, experiment, tmp_path)

        mock_create_job.assert_called_once()
        assert mock_create_job.call_args.kwargs["resources"] == ANALYSIS_RESOURCES
        assert mock_create_job.call_args.kwargs["name"] == f"analysis-{job.id}"

    async def test_replaces_previous_analyses_of_the_simulation(self, db_session: AsyncSession, tmp_path: Path) -> None:
        """A new analysis deletes the simulation's previous analysis Job and row."""
        experiment = await _experiment(db_session)
        with (
            patch("models.analysis_job.k8s.check_quota_headroom", AsyncMock(return_value=None)),
            patch("models.analysis_job.k8s.create_job"),
            patch("models.analysis_job.k8s.delete_job") as mock_delete_job,
        ):
            first = await _start(db_session, experiment, tmp_path)
            second = await _start(db_session, experiment, tmp_path)

        mock_delete_job.assert_called_once_with(f"analysis-{first.id}")
        assert await db_session.get(AnalysisJob, first.id) is None
        assert await db_session.get(AnalysisJob, second.id) is not None


class TestAnalysisJobStartSimProgress:
    """Tests for the simulation-progress snapshot in AnalysisJob.start()."""

    async def _progress(
        self, db_session: AsyncSession, tmp_path: Path, nsteps: int | None, done: int | None
    ) -> float | None:
        experiment = await _experiment(db_session, nsteps)
        with (
            patch("models.analysis_job.k8s.check_quota_headroom", AsyncMock(return_value=None)),
            patch("models.analysis_job.k8s.create_job"),
            patch.object(GromacsJob, "nsteps_done", new_callable=PropertyMock, return_value=done),
        ):
            job = await _start(db_session, experiment, tmp_path)
        return job.sim_progress

    async def test_records_progress_fraction_from_run_job(self, db_session: AsyncSession, tmp_path: Path) -> None:
        """A mid-run simulation's progress is snapshotted onto the new analysis job."""
        assert await self._progress(db_session, tmp_path, nsteps=200, done=40) == pytest.approx(0.2)

    async def test_progress_is_none_without_run_job(self, db_session: AsyncSession, tmp_path: Path) -> None:
        """No run job for the simulation means no progress to snapshot."""
        assert await self._progress(db_session, tmp_path, nsteps=None, done=None) is None

    async def test_progress_is_none_when_done_is_unknown(self, db_session: AsyncSession, tmp_path: Path) -> None:
        """Unknown nsteps_done cannot produce a truthful fraction."""
        assert await self._progress(db_session, tmp_path, nsteps=200, done=None) is None

    async def test_progress_clamped_at_one(self, db_session: AsyncSession, tmp_path: Path) -> None:
        """A finished run must not report more than 100%."""
        assert await self._progress(db_session, tmp_path, nsteps=200, done=250) == 1.0


class TestAnalysisJobStatus:
    """Remote status is fetched once per refresh; settled jobs never ask K8s again."""

    async def test_finished_job_cleans_temp_files_once(self, tmp_path: Path) -> None:
        job = AnalysisJob(
            id="a1", experiment_id="exptt", simulation_path="x.simulation.json", analysis_name=AnalysisType.RMSDS
        )
        (tmp_path / "exptt").mkdir()
        (tmp_path / "exptt" / "inputs.yaml").write_text("x")
        with patch("models.analysis_job.k8s.get_job_status", AsyncMock(return_value=JobStatus.FINISHED)) as status:
            assert await job.refresh_status() == JobStatus.FINISHED
            assert await job.refresh_status() == JobStatus.FINISHED

        status.assert_awaited_once()
        assert job.status == JobStatus.FINISHED
        assert not (tmp_path / "exptt" / "inputs.yaml").exists()

    async def test_unreachable_k8s_falls_back_to_last_known(self) -> None:
        job = AnalysisJob(
            id="a2",
            experiment_id="exptt",
            simulation_path="x.simulation.json",
            analysis_name=AnalysisType.RMSDS,
            _last_known_status=JobStatus.RUNNING,
        )
        with patch("models.analysis_job.k8s.get_job_status", AsyncMock(side_effect=RuntimeError("down"))):
            assert await job.refresh_status() == JobStatus.RUNNING
