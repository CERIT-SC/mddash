"""Unit tests for the structured Experiment source."""

from pathlib import Path
from unittest.mock import patch

from enums import SourceType
from models import Experiment


class TestSourcePayload:
    def test_no_source_is_none(self) -> None:
        assert Experiment(id="src01", name="Legacy").source is None

    def test_pdb_id_source(self) -> None:
        source = Experiment(id="src02", name="PDB", source_type=SourceType.PDB, source_ref="1LYZ").source
        assert source is not None
        assert source["type"] == "pdb"
        assert source["pdb_id"] == "1LYZ"
        assert "url" not in source
        assert source["files"] == []

    def test_pdb_url_source(self) -> None:
        source = Experiment(
            id="src03", name="PDB URL", source_type=SourceType.PDB, source_ref="https://example.org/x.pdb"
        ).source
        assert source is not None
        assert source["type"] == "pdb"
        assert source["url"] == "https://example.org/x.pdb"
        assert "pdb_id" not in source

    def test_repo_source_has_no_files(self) -> None:
        source = Experiment(
            id="src04", name="Repo", source_type=SourceType.REPO, source_ref="https://zenodo.org/records/1"
        ).source
        assert source is not None
        assert source["type"] == "repo"
        assert source["url"] == "https://zenodo.org/records/1"
        assert source["files"] == []


class TestSourceFiles:
    def test_pdb_lists_input_pdb_when_present(self, tmp_path: Path) -> None:
        (tmp_path / "src05").mkdir()
        (tmp_path / "src05" / "input.pdb").write_bytes(b"ATOM    1  N   GLY A   1\n")
        with patch("models.experiment.DATA_DIR", tmp_path):
            source = Experiment(id="src05", name="PDB", source_type=SourceType.PDB, source_ref="1LYZ").source
        assert source is not None
        assert [f["name"] for f in source["files"]] == ["input.pdb"]
        assert source["files"][0]["size"] == len("ATOM    1  N   GLY A   1\n")
        assert source["files"][0]["url"].endswith("/experiments/src05/files/input.pdb")

    def test_file_source_lists_uploads_that_still_exist(self, tmp_path: Path) -> None:
        (tmp_path / "src06").mkdir()
        (tmp_path / "src06" / "b.pdb").write_bytes(b"bb")
        (tmp_path / "src06" / "a.tpr").write_bytes(b"a")
        with patch("models.experiment.DATA_DIR", tmp_path):
            source = Experiment(
                id="src06", name="Files", source_type=SourceType.FILE, source_files=["b.pdb", "a.tpr", "gone.xtc"]
            ).source
        assert source is not None
        assert [f["name"] for f in source["files"]] == ["a.tpr", "b.pdb"]
        # Creation history outlives deleted files.
        assert source["file_count"] == 3
