"""Unit tests for the safe same-filesystem merge of staged repository content."""

import os
from pathlib import Path
from types import SimpleNamespace

import pytest
from modules.population.merge import PopulationMergeError, merge_staged


@pytest.fixture
def fs(tmp_path: Path) -> SimpleNamespace:
    """Prepare a staging tree and a prepared experiment directory on the same filesystem."""
    staging = tmp_path / ".cache" / "datahugger" / "op1" / "data"
    experiment = tmp_path / "abcde"
    staging.mkdir(parents=True)
    experiment.mkdir()
    return SimpleNamespace(staging=staging, experiment=experiment)


def _write(path: Path, content: str = "x") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


class TestMergeStaged:
    """Repository content lands at the experiment root, layout intact, notebooks untouched."""

    def test_moves_tree_preserving_layout(self, fs: SimpleNamespace) -> None:
        _write(fs.staging / "files" / "a.pdb", "A")
        _write(fs.staging / "sub" / "b.txt", "B")
        _write(fs.staging / "top.txt", "T")
        _write(fs.experiment / "notebooks.ipynb", "nb")

        merge_staged(fs.staging, fs.experiment)

        assert (fs.experiment / "files" / "a.pdb").read_text() == "A"
        assert (fs.experiment / "sub" / "b.txt").read_text() == "B"
        assert (fs.experiment / "top.txt").read_text() == "T"
        assert (fs.experiment / "notebooks.ipynb").read_text() == "nb"
        # Rename, not copy: nothing is left in staging.
        assert list(fs.staging.rglob("*")) == []

    def test_rename_preserves_the_inode(self, fs: SimpleNamespace) -> None:
        _write(fs.staging / "top.txt", "T")
        inode = (fs.staging / "top.txt").stat().st_ino

        merge_staged(fs.staging, fs.experiment)

        assert (fs.experiment / "top.txt").stat().st_ino == inode

    def test_allows_compatible_directory_overlap(self, fs: SimpleNamespace) -> None:
        _write(fs.staging / "sub" / "b.txt", "B")
        _write(fs.experiment / "sub" / "a.txt", "A")

        merge_staged(fs.staging, fs.experiment)

        assert (fs.experiment / "sub" / "a.txt").read_text() == "A"
        assert (fs.experiment / "sub" / "b.txt").read_text() == "B"

    def test_allows_nested_directory_overlap(self, fs: SimpleNamespace) -> None:
        _write(fs.staging / "sub" / "nested" / "c.txt", "C")
        _write(fs.experiment / "sub" / "nested" / "d.txt", "D")
        _write(fs.experiment / "sub" / "a.txt", "A")

        merge_staged(fs.staging, fs.experiment)

        assert (fs.experiment / "sub" / "a.txt").read_text() == "A"
        assert (fs.experiment / "sub" / "nested" / "c.txt").read_text() == "C"
        assert (fs.experiment / "sub" / "nested" / "d.txt").read_text() == "D"
        assert list(fs.staging.rglob("*")) == []

    def test_missing_staging_is_rejected(self, tmp_path: Path) -> None:
        with pytest.raises(PopulationMergeError, match="missing or empty"):
            merge_staged(tmp_path / "no-such-staging", tmp_path / "abcde")

    def test_rejects_symlink_anywhere_in_the_tree(self, fs: SimpleNamespace) -> None:
        _write(fs.staging / "top.txt", "T")
        (fs.staging / "sub").mkdir()
        (fs.staging / "sub" / "link").symlink_to("/etc/passwd")

        with pytest.raises(PopulationMergeError, match="Symlinks are not allowed"):
            merge_staged(fs.staging, fs.experiment)

        # Validation precedes any move: the experiment is untouched, staging intact.
        assert list(fs.experiment.iterdir()) == []
        assert (fs.staging / "top.txt").is_file()

    def test_rejects_special_files(self, fs: SimpleNamespace) -> None:
        _write(fs.staging / "top.txt", "T")
        os.mkfifo(str(fs.staging / "pipe"))

        with pytest.raises(PopulationMergeError, match="Special files are not allowed"):
            merge_staged(fs.staging, fs.experiment)
        assert list(fs.experiment.iterdir()) == []

    def test_file_collision_keeps_both(self, fs: SimpleNamespace) -> None:
        _write(fs.staging / "README.md", "S")
        _write(fs.staging / ".gitignore", "S")
        _write(fs.staging / "LICENSE", "S")
        _write(fs.staging / "sub" / "a.txt", "S")
        for name in ("README.md", ".gitignore", "LICENSE", "sub/a.txt"):
            _write(fs.experiment / name, "E")

        renamed = merge_staged(fs.staging, fs.experiment)

        assert sorted(renamed) == [".gitignore.dataset", "LICENSE.dataset", "README.dataset.md", "sub/a.dataset.txt"]
        for name in renamed:
            assert (fs.experiment / name).read_text() == "S"
        for name in ("README.md", ".gitignore", "LICENSE", "sub/a.txt"):
            assert (fs.experiment / name).read_text() == "E"

    def test_renamed_name_skips_taken_names(self, fs: SimpleNamespace) -> None:
        _write(fs.staging / "README.md", "S")
        _write(fs.experiment / "README.md", "E")
        _write(fs.experiment / "README.dataset.md", "E2")

        assert merge_staged(fs.staging, fs.experiment) == ["README.dataset-2.md"]
        assert (fs.experiment / "README.dataset-2.md").read_text() == "S"
        assert (fs.experiment / "README.dataset.md").read_text() == "E2"

    @pytest.mark.parametrize(
        ("staged", "existing"),
        [("sub", "sub/a.txt"), ("sub/a.txt", "sub")],
        ids=["staged-file-vs-dir", "staged-dir-vs-file"],
    )
    def test_file_dir_collision_keeps_both(self, fs: SimpleNamespace, staged: str, existing: str) -> None:
        _write(fs.staging / staged, "S")
        _write(fs.experiment / existing, "E")

        assert merge_staged(fs.staging, fs.experiment) == ["sub.dataset"]
        assert (fs.experiment / existing).read_text() == "E"
        assert (fs.experiment / "sub.dataset" / Path(staged).relative_to("sub")).read_text() == "S"
