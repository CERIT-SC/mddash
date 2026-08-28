"""Unit tests for analysis job mwf command generation."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from config import ANALYSIS_RESOURCES
from enums import AnalysisType, PreprocessingMode
from models.analysis_job import (
    AnalysisJob,
    format_mwf_analysis_command,
    format_mwf_inputs_yaml,
    get_analysis_runtime_prep_commands,
    get_incomplete_task_dirs,
    get_runtime_prelude_commands,
)
from werkzeug.exceptions import Forbidden


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


class TestAnalysisJobStartQuotaCheck:
    """Tests for the quota-headroom guard in AnalysisJob.start()."""

    def _mock_experiment(self) -> MagicMock:
        exp = MagicMock()
        exp.id = "exp-test"
        return exp

    def test_raises_forbidden_when_quota_exceeded(self, app: object, tmp_path: Path) -> None:
        """start() must raise Forbidden and not create a job when quota is insufficient."""
        with (
            patch("models.analysis_job.k8s.check_quota_headroom", return_value="CPU quota exceeded"),
            patch("models.analysis_job.k8s.create_job") as mock_create_job,
            patch("models.analysis_job.k8s.delete_job"),
            patch.object(AnalysisJob, "query") as mock_query,
            patch("models.analysis_job.db.session"),
            patch("models.analysis_job.SimulationJob") as mock_sim_job,
        ):
            mock_query.filter_by.return_value.all.return_value = []
            mock_sim_job.query.filter_by.return_value.order_by.return_value.first.return_value = None
            structure_file = tmp_path / "input.gro"
            structure_file.touch()
            trajectory_file = tmp_path / "traj.xtc"
            trajectory_file.touch()

            with pytest.raises(Forbidden):
                AnalysisJob.start(
                    experiment=self._mock_experiment(),
                    simulation_path="test.simulation.json",
                    analysis_name=AnalysisType.RMSDS,
                    structure_file=structure_file,
                    trajectory_file=trajectory_file,
                    topology_file=None,
                    preprocessing_mode=PreprocessingMode.AS_IS,
                )

            mock_create_job.assert_not_called()

    def test_creates_job_with_analysis_resources_when_headroom_sufficient(self, app: object, tmp_path: Path) -> None:
        """start() must pass ANALYSIS_RESOURCES to create_job when quota has headroom."""
        with (
            patch("models.analysis_job.k8s.check_quota_headroom", return_value=None),
            patch("models.analysis_job.k8s.create_job") as mock_create_job,
            patch("models.analysis_job.k8s.delete_job"),
            patch.object(AnalysisJob, "query") as mock_query,
            patch("models.analysis_job.db.session"),
            patch("models.analysis_job.SimulationJob") as mock_sim_job,
        ):
            mock_query.filter_by.return_value.all.return_value = []
            mock_sim_job.query.filter_by.return_value.order_by.return_value.first.return_value = None
            structure_file = tmp_path / "input.gro"
            structure_file.touch()
            trajectory_file = tmp_path / "traj.xtc"
            trajectory_file.touch()

            AnalysisJob.start(
                experiment=self._mock_experiment(),
                simulation_path="test.simulation.json",
                analysis_name=AnalysisType.RMSDS,
                structure_file=structure_file,
                trajectory_file=trajectory_file,
                topology_file=None,
                preprocessing_mode=PreprocessingMode.AS_IS,
            )

            mock_create_job.assert_called_once()
            assert mock_create_job.call_args.kwargs["resources"] == ANALYSIS_RESOURCES


class TestAnalysisJobStartSimProgress:
    """Tests for the simulation-progress snapshot in AnalysisJob.start()."""

    def _start(self, mock_session: MagicMock, tmp_path: Path) -> float | None:
        exp = MagicMock()
        exp.id = "exp-test"
        trajectory_file = tmp_path / "traj.xtc"
        trajectory_file.touch()
        topology_file = tmp_path / "topol.tpr"
        topology_file.touch()
        AnalysisJob.start(
            experiment=exp,
            simulation_path="test.simulation.json",
            analysis_name=AnalysisType.RMSDS,
            structure_file=None,
            trajectory_file=trajectory_file,
            topology_file=topology_file,
            preprocessing_mode=PreprocessingMode.AS_IS,
        )
        job: AnalysisJob = mock_session.add.call_args[0][0]
        return job.sim_progress

    def _patched_start(self, run_job: MagicMock | None, app: object, tmp_path: Path) -> float | None:
        with (
            patch("models.analysis_job.k8s.check_quota_headroom", return_value=None),
            patch("models.analysis_job.k8s.create_job"),
            patch("models.analysis_job.k8s.delete_job"),
            patch.object(AnalysisJob, "query") as mock_query,
            patch("models.analysis_job.db.session") as mock_session,
            patch("models.analysis_job.SimulationJob") as mock_sim_job,
        ):
            mock_query.filter_by.return_value.all.return_value = []
            mock_sim_job.query.filter_by.return_value.order_by.return_value.first.return_value = run_job
            return self._start(mock_session, tmp_path)

    def test_records_progress_fraction_from_run_job(self, app: object, tmp_path: Path) -> None:
        """A mid-run simulation's progress is snapshotted onto the new analysis job."""
        run_job = MagicMock(nsteps=200, nsteps_done=40)
        assert self._patched_start(run_job, app, tmp_path) == pytest.approx(0.2)

    def test_progress_is_none_without_run_job(self, app: object, tmp_path: Path) -> None:
        """No run job for the simulation means no progress to snapshot."""
        assert self._patched_start(None, app, tmp_path) is None

    def test_progress_is_none_when_done_is_unknown(self, app: object, tmp_path: Path) -> None:
        """Unknown nsteps_done cannot produce a truthful fraction."""
        run_job = MagicMock(nsteps=200, nsteps_done=None)
        assert self._patched_start(run_job, app, tmp_path) is None

    def test_progress_clamped_at_one(self, app: object, tmp_path: Path) -> None:
        """A finished run must not report more than 100%."""
        run_job = MagicMock(nsteps=200, nsteps_done=250)
        assert self._patched_start(run_job, app, tmp_path) == 1.0
