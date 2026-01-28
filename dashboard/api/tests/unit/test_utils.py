"""Unit tests for utility functions."""

from pathlib import Path

import pytest
from utils import (
    generate_id,
    get_files_with_extensions,
    get_unique_id,
    is_excluded_path,
    validate_git_url,
)
from werkzeug.exceptions import BadRequest

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

    def test_skips_excluded_files(self, tmp_path: Path) -> None:
        """Should skip files matching excluded file patterns."""
        (tmp_path / "keep.pdb").touch()
        (tmp_path / "notes.tmp").touch()

        result = get_files_with_extensions(tmp_path, ["pdb", "tmp"])

        names = [f["name"] for f in result]
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


class TestValidateGitUrl:
    """Tests for the validate_git_url function."""

    def test_accepts_https_github_url(self) -> None:
        """Should accept valid HTTPS GitHub URLs."""
        validate_git_url("https://github.com/owner/repo.git")  # Should not raise

    def test_accepts_https_gitlab_url(self) -> None:
        """Should accept valid HTTPS GitLab URLs."""
        validate_git_url("https://gitlab.com/owner/repo.git")  # Should not raise

    def test_accepts_ssh_url(self) -> None:
        """Should accept valid SSH git URLs."""
        validate_git_url("git@github.com:owner/repo.git")  # Should not raise

    def test_accepts_http_url(self) -> None:
        """Should accept HTTP URLs (though not recommended)."""
        validate_git_url("http://github.com/owner/repo.git")  # Should not raise

    def test_rejects_empty_url(self) -> None:
        """Should reject empty URLs."""
        with pytest.raises(BadRequest):
            validate_git_url("")

    def test_rejects_whitespace_only(self) -> None:
        """Should reject whitespace-only URLs."""
        with pytest.raises(BadRequest):
            validate_git_url("   ")

    def test_rejects_option_injection(self) -> None:
        """Should reject URLs starting with dash (option injection)."""
        with pytest.raises(BadRequest):
            validate_git_url("--upload-pack=malicious")

    def test_rejects_local_absolute_path(self) -> None:
        """Should reject local absolute paths."""
        with pytest.raises(BadRequest):
            validate_git_url("/etc/passwd")

    def test_rejects_local_relative_path(self) -> None:
        """Should reject local relative paths."""
        with pytest.raises(BadRequest):
            validate_git_url("./local/repo")

    def test_rejects_file_protocol(self) -> None:
        """Should reject file:// URLs."""
        with pytest.raises(BadRequest):
            validate_git_url("file:///etc/passwd")

    def test_rejects_url_with_credentials(self) -> None:
        """Should reject URLs with embedded credentials."""
        with pytest.raises(BadRequest):
            validate_git_url("https://user:password@github.com/owner/repo.git")

    def test_rejects_url_with_username_only(self) -> None:
        """Should reject URLs with embedded username."""
        with pytest.raises(BadRequest):
            validate_git_url("https://user@github.com/owner/repo.git")

    def test_rejects_ftp_protocol(self) -> None:
        """Should reject unsupported protocols like ftp."""
        with pytest.raises(BadRequest):
            validate_git_url("ftp://server.com/repo.git")
