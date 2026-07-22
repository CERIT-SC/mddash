"""Unit tests for utility functions."""

import contextlib
from pathlib import Path

from pytest_mock import MockerFixture
from utils import (
    generate_id,
    get_files_with_extensions,
    get_unique_id,
    is_excluded_path,
)

DEFAULT_ID_LENGTH = 5
CUSTOM_ID_LENGTH = 10
RANDOM_SAMPLES_COUNT = 100


class TestGenerateId:
    """Tests for the generate_id function."""

    def test_default_length(self) -> None:
        """Generated ID should be 5 characters by default."""
        result = generate_id()
        assert len(result) == DEFAULT_ID_LENGTH

    def test_custom_length(self) -> None:
        """Generated ID should respect custom length parameter."""
        result = generate_id(CUSTOM_ID_LENGTH)
        assert len(result) == CUSTOM_ID_LENGTH

    def test_only_lowercase_letters(self) -> None:
        """Generated ID should only contain lowercase letters."""
        for _ in range(RANDOM_SAMPLES_COUNT):  # Run multiple times to catch randomness issues
            result = generate_id()
            assert result.isalpha()
            assert result.islower()

    def test_randomness(self) -> None:
        """Generated IDs should be random (not always the same)."""
        ids = {generate_id() for _ in range(RANDOM_SAMPLES_COUNT)}
        assert len(ids) > 1  # collisions possible (birthday problem), don't assert uniqueness


class TestGetUniqueId:
    """Tests for the get_unique_id function."""

    def test_returns_unique_id(self, tmp_path: Path) -> None:
        """Should return an ID not present in the directory."""
        result = get_unique_id(tmp_path)
        assert len(result) == DEFAULT_ID_LENGTH
        assert not (tmp_path / result).exists()

    def test_avoids_existing_directories(self, tmp_path: Path) -> None:
        """Should not return an ID that already exists as a directory."""
        # Create some existing directories
        existing = ["aaaaa", "bbbbb", "ccccc"]
        for name in existing:
            (tmp_path / name).mkdir()

        # Generate many IDs and ensure none match existing
        for _ in range(50):
            result = get_unique_id(tmp_path)
            assert result not in existing


class TestGetFilesWithExtensions:
    """Tests for the get_files_with_extensions function."""

    def test_finds_files_with_extension(self, tmp_path: Path) -> None:
        """Should find files matching the given extensions."""
        # Create test files
        (tmp_path / "file1.pdb").touch()
        (tmp_path / "file2.xtc").touch()
        (tmp_path / "file3.txt").touch()

        result = get_files_with_extensions(tmp_path, ["pdb", "xtc"])

        found_files_count = 2
        assert len(result) == found_files_count
        names = [f.name for f in result]
        paths = [f.path for f in result]
        assert "file1.pdb" in names
        assert "file2.xtc" in names
        assert "file3.txt" not in names
        assert "file1.pdb" in paths
        assert "file2.xtc" in paths

    def test_returns_empty_for_no_matches(self, tmp_path: Path) -> None:
        """Should return empty list when no files match."""
        (tmp_path / "file.txt").touch()
        result = get_files_with_extensions(tmp_path, ["pdb"])

        assert result == []

    def test_handles_empty_directory(self, tmp_path: Path) -> None:
        """Should handle empty directories gracefully."""
        result = get_files_with_extensions(tmp_path, ["pdb"])
        assert result == []

    def test_skips_excluded_files(self, tmp_path: Path) -> None:
        """Should skip files matching excluded file patterns."""
        (tmp_path / "keep.pdb").touch()
        (tmp_path / "notes.tmp").touch()

        result = get_files_with_extensions(tmp_path, ["pdb", "tmp"])

        names = [f.name for f in result]
        assert "keep.pdb" in names
        assert "notes.tmp" not in names


class TestIsExcludedPath:
    """Tests for the is_excluded_path function."""

    def test_allows_simulation_files(self, tmp_path: Path) -> None:
        """Simulation files should not be excluded by directory patterns."""
        file_path = tmp_path / "trajectory.xtc"
        file_path.touch()

        assert is_excluded_path(file_path, tmp_path) is False

    def test_excludes_temp_files(self, tmp_path: Path) -> None:
        """Temporary files should be excluded by file patterns."""
        file_path = tmp_path / "#scratch#"
        file_path.touch()

        assert is_excluded_path(file_path, tmp_path) is True

    def test_excludes_directories_matching_patterns(self, tmp_path: Path) -> None:
        """Directories named like excluded patterns should be excluded."""
        excluded_dir = tmp_path / "data.xtc"
        excluded_dir.mkdir()
        nested_file = excluded_dir / "payload.txt"
        nested_file.touch()

        assert is_excluded_path(nested_file, tmp_path) is True


class TestDuMonitor:
    """Tests for storage-size monitor startup."""

    def test_start_du_monitor_passes_initial_delay_to_thread(self, tmp_path: Path, mocker: MockerFixture) -> None:
        """The first du scan should be delayable to avoid first-health IO contention."""
        thread_cls = mocker.patch("utils.threading.Thread")
        mocker.patch("utils.threading.enumerate", return_value=[])

        from utils import start_du_monitor

        start_du_monitor(tmp_path, initial_delay=7.5)

        thread_cls.assert_called_once()
        assert thread_cls.call_args.kwargs["args"] == (tmp_path, 7.5)
        thread_cls.return_value.start.assert_called_once_with()

    def test_du_loop_sleeps_before_first_measurement_when_initial_delay_set(
        self, tmp_path: Path, mocker: MockerFixture
    ) -> None:
        """A configured initial delay should happen before subprocess du runs."""
        sleep = mocker.patch("utils.time.sleep", side_effect=RuntimeError("stop"))
        run = mocker.patch("utils.subprocess.run")

        from utils import _du_loop  # ruff:ignore[import-private-name]

        with contextlib.suppress(RuntimeError):
            _du_loop(tmp_path, initial_delay=3.0)

        sleep.assert_called_once_with(3.0)
        run.assert_not_called()
