"""Unit tests for analysis job mwf command generation."""

from pathlib import Path

from enums import AnalysisType, PreprocessingMode
from models.analysis_job import (
    format_mwf_analysis_command,
    format_mwf_inputs_yaml,
    get_analysis_runtime_prep_commands,
    get_incomplete_task_dirs,
    get_runtime_prelude_commands,
)


class TestFormatMwfInputsYaml:
    """Tests for per-analysis mwf inputs generation."""

    def test_includes_auto_interactions_for_interaction_driven_analysis(self) -> None:
        """Hydrogen bond analysis should request automatic interaction processing."""
        content = format_mwf_inputs_yaml(AnalysisType.HBONDS)

        assert content == "name: mddash\ntype: trajectory\ninteractions:\n  - auto\n"

    def test_omits_auto_interactions_for_clusters(self) -> None:
        """Clusters should not force automatic interactions for the overall run."""
        content = format_mwf_inputs_yaml(AnalysisType.CLUSTERS)

        assert content == "name: mddash\ntype: trajectory\n"


class TestFormatMwfAnalysisCommand:
    """Tests for mwf shell command construction."""

    def test_incomplete_task_dirs_cover_project_and_md_roots(self) -> None:
        """Incomplete task directories should cover both project-relative and MD-relative roots."""
        assert get_incomplete_task_dirs("inter") == [
            Path("incomplete_inter"),
            Path("mwf_analyses") / "incomplete_inter",
        ]

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
        )

        assert "interactions:" not in command
        assert "mkdir -p incomplete_clusters mwf_analyses/incomplete_clusters" in command
        assert "-i clusters" in command

    def test_clusters_runtime_prep_covers_project_and_md_relative_temp_dirs(self) -> None:
        """Clusters prep should create temp screenshot directories for both path-resolution variants."""
        commands = get_analysis_runtime_prep_commands(AnalysisType.CLUSTERS)

        assert commands == ["mkdir -p incomplete_clusters mwf_analyses/incomplete_clusters"]

    def test_hbonds_runtime_prep_covers_project_and_md_relative_inter_dirs(self) -> None:
        """Interaction-driven analyses should create temp interaction directories for both path anchors."""
        commands = get_analysis_runtime_prep_commands(AnalysisType.HBONDS)

        assert commands == ["mkdir -p incomplete_inter mwf_analyses/incomplete_inter"]

    def test_hbonds_command_injects_auto_interactions(self) -> None:
        """Hydrogen bond command should request automatic interactions."""
        command = format_mwf_analysis_command(
            analysis_name=AnalysisType.HBONDS,
            structure_file=Path("input.gro"),
            trajectory_file=Path("traj.xtc"),
            topology_file=None,
            preprocessing_mode=PreprocessingMode.AS_IS,
        )

        assert "interactions:" in command
        assert "  - auto" in command
        assert "mkdir -p incomplete_inter mwf_analyses/incomplete_inter" in command
        assert "-i hbonds" in command
