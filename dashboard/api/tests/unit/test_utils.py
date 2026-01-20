"""Unit tests for utility functions."""

from pathlib import Path

from utils import (
    generate_id,
    get_files_with_extensions,
    get_unique_id,
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
        # With 26^5 possible IDs, 100 samples should all be unique
        assert len(ids) == RANDOM_SAMPLES_COUNT


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
        names = [f["name"] for f in result]
        assert "file1.pdb" in names
        assert "file2.xtc" in names
        assert "file3.txt" not in names

    def test_returns_empty_for_no_matches(self, tmp_path: Path) -> None:
        """Should return empty list when no files match."""
        (tmp_path / "file.txt").touch()
        result = get_files_with_extensions(tmp_path, ["pdb"])

        assert result == []

    def test_handles_empty_directory(self, tmp_path: Path) -> None:
        """Should handle empty directories gracefully."""
        result = get_files_with_extensions(tmp_path, ["pdb"])
        assert result == []
