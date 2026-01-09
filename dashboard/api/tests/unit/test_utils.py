"""Unit tests for utility functions."""

from pathlib import Path


class TestGenerateId:
    """Tests for the generate_id function."""

    def test_default_length(self) -> None:
        """Generated ID should be 5 characters by default."""
        from utils import generate_id

        result = generate_id()
        assert len(result) == 5

    def test_custom_length(self) -> None:
        """Generated ID should respect custom length parameter."""
        from utils import generate_id

        result = generate_id(10)
        assert len(result) == 10

    def test_only_lowercase_letters(self) -> None:
        """Generated ID should only contain lowercase letters."""
        from utils import generate_id

        for _ in range(100):  # Run multiple times to catch randomness issues
            result = generate_id()
            assert result.isalpha()
            assert result.islower()

    def test_randomness(self) -> None:
        """Generated IDs should be random (not always the same)."""
        from utils import generate_id

        ids = {generate_id() for _ in range(100)}
        # With 26^5 possible IDs, 100 samples should all be unique
        assert len(ids) == 100


class TestGetUniqueId:
    """Tests for the get_unique_id function."""

    def test_returns_unique_id(self, tmp_path: Path) -> None:
        """Should return an ID not present in the directory."""
        from utils import get_unique_id

        result = get_unique_id(tmp_path)
        assert len(result) == 5
        assert not (tmp_path / result).exists()

    def test_avoids_existing_directories(self, tmp_path: Path) -> None:
        """Should not return an ID that already exists as a directory."""
        from utils import get_unique_id

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
        from utils import get_files_with_extensions

        # Create test files
        (tmp_path / "file1.pdb").touch()
        (tmp_path / "file2.xtc").touch()
        (tmp_path / "file3.txt").touch()

        result = get_files_with_extensions(tmp_path, ["pdb", "xtc"])

        assert len(result) == 2
        names = [f["name"] for f in result]
        assert "file1.pdb" in names
        assert "file2.xtc" in names
        assert "file3.txt" not in names

    def test_returns_empty_for_no_matches(self, tmp_path: Path) -> None:
        """Should return empty list when no files match."""
        from utils import get_files_with_extensions

        (tmp_path / "file.txt").touch()
        result = get_files_with_extensions(tmp_path, ["pdb"])

        assert result == []

    def test_handles_empty_directory(self, tmp_path: Path) -> None:
        """Should handle empty directories gracefully."""
        from utils import get_files_with_extensions

        result = get_files_with_extensions(tmp_path, ["pdb"])
        assert result == []
