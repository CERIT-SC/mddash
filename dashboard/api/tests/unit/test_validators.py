"""Unit tests for input validators."""

from pathlib import Path

import pytest
from enums import AnalysisType, PreprocessingMode
from validators import (
    check_experiment_id,
    check_filename,
    check_log_type,
    check_path,
    check_positive_int,
    validate_analysis_topology_path,
    validate_git_url,
)
from werkzeug.exceptions import BadRequest, Forbidden


class TestCheckExperimentId:
    """Tests for the check_experiment_id function."""

    def test_accepts_valid_id(self) -> None:
        """Valid 5-character lowercase ID should be accepted."""
        check_experiment_id("abcde")  # Should not raise

    def test_rejects_empty_string(self) -> None:
        """Empty string should be rejected."""
        with pytest.raises(BadRequest):
            check_experiment_id("")

    def test_rejects_too_short(self) -> None:
        """ID shorter than 5 characters should be rejected."""
        with pytest.raises(BadRequest):
            check_experiment_id("abcd")

    def test_rejects_too_long(self) -> None:
        """ID longer than 5 characters should be rejected."""
        with pytest.raises(BadRequest):
            check_experiment_id("abcdef")

    def test_rejects_uppercase(self) -> None:
        """ID containing uppercase letters should be rejected."""
        with pytest.raises(BadRequest):
            check_experiment_id("Abcde")

    def test_rejects_digits(self) -> None:
        """ID containing digits should be rejected."""
        with pytest.raises(BadRequest):
            check_experiment_id("abc12")

    def test_rejects_special_characters(self) -> None:
        """ID containing special characters should be rejected."""
        with pytest.raises(BadRequest):
            check_experiment_id("ab-de")


class TestCheckFilename:
    """Tests for the check_filename function."""

    def test_accepts_valid_filename(self) -> None:
        """Plain filename with extension should be accepted."""
        check_filename("file.txt")  # Should not raise

    def test_rejects_empty_filename(self) -> None:
        """Empty filename should be rejected."""
        with pytest.raises(BadRequest):
            check_filename("")

    def test_rejects_path_traversal_with_dotdot(self) -> None:
        """Filename with '..' path traversal should be rejected."""
        with pytest.raises(BadRequest):
            check_filename("../etc/passwd")

    def test_rejects_path_with_slash(self) -> None:
        """Filename containing a forward slash should be rejected."""
        with pytest.raises(BadRequest):
            check_filename("dir/file.txt")

    def test_rejects_path_with_backslash(self) -> None:
        """Filename containing a backslash should be rejected."""
        with pytest.raises(BadRequest):
            check_filename("dir\\file.txt")

    def test_rejects_hidden_file(self) -> None:
        """Filename starting with '.' should be rejected."""
        with pytest.raises(BadRequest):
            check_filename(".hidden")

    def test_rejects_tilde_file(self) -> None:
        """Filename starting with '~' should be rejected."""
        with pytest.raises(BadRequest):
            check_filename("~backup")

    def test_rejects_null_byte(self) -> None:
        """Filename containing a null byte should be rejected."""
        with pytest.raises(BadRequest):
            check_filename("file\x00.txt")

    def test_accepts_allowed_extension(self) -> None:
        """Filename with an extension in the allowed list should be accepted."""
        check_filename("topology.tpr", allowed_extensions=["tpr", "gro"])  # Should not raise

    def test_rejects_disallowed_extension(self) -> None:
        """Filename with an extension not in the allowed list should be rejected."""
        with pytest.raises(BadRequest):
            check_filename("script.sh", allowed_extensions=["tpr", "gro"])

    def test_rejects_no_extension_when_extensions_required(self) -> None:
        """Filename with no extension should be rejected when extensions are required."""
        with pytest.raises(BadRequest):
            check_filename("noextension", allowed_extensions=["tpr"])

    def test_skips_extension_check_when_none(self) -> None:
        """Any extension should be accepted when allowed_extensions is not provided."""
        check_filename("anything.sh")  # Should not raise when allowed_extensions is None


class TestCheckPath:
    """Tests for the check_path function."""

    def test_accepts_valid_path(self, tmp_path: Path) -> None:
        """Path within the base directory should be accepted."""
        (tmp_path / "subdir").mkdir()
        check_path("subdir", tmp_path)  # Should not raise

    def test_rejects_empty_path(self, tmp_path: Path) -> None:
        """Empty path should be rejected."""
        with pytest.raises(BadRequest):
            check_path("", tmp_path)

    def test_rejects_null_byte(self, tmp_path: Path) -> None:
        """Path containing a null byte should be rejected."""
        with pytest.raises(BadRequest):
            check_path("file\x00name", tmp_path)

    def test_rejects_path_traversal(self, tmp_path: Path) -> None:
        """Path escaping the base directory should be rejected."""
        with pytest.raises(Forbidden):
            check_path("../../etc/passwd", tmp_path)

    def test_accepts_nested_path(self, tmp_path: Path) -> None:
        """Nested path within the base directory should be accepted."""
        (tmp_path / "a" / "b").mkdir(parents=True)
        check_path("a/b", tmp_path)  # Should not raise


class TestCheckLogType:
    """Tests for the check_log_type function."""

    def test_accepts_gmx(self) -> None:
        """Log type 'gmx' should be accepted."""
        check_log_type("gmx")  # Should not raise

    def test_accepts_stdout(self) -> None:
        """Log type 'stdout' should be accepted."""
        check_log_type("stdout")  # Should not raise

    def test_accepts_stderr(self) -> None:
        """Log type 'stderr' should be accepted."""
        check_log_type("stderr")  # Should not raise

    def test_rejects_invalid_type(self) -> None:
        """Unknown log type should be rejected."""
        with pytest.raises(BadRequest):
            check_log_type("syslog")

    def test_rejects_empty_string(self) -> None:
        """Empty log type should be rejected."""
        with pytest.raises(BadRequest):
            check_log_type("")


class TestValidateAnalysisTopologyPath:
    """Tests for analysis topology validation across preprocessing modes."""

    def test_allows_missing_topology_for_as_is_non_topology_analysis(self, tmp_path: Path) -> None:
        """As-is mode should not require topology for analyses that do not depend on it."""
        assert (
            validate_analysis_topology_path(
                topology_file=None,
                experiment_dir=tmp_path,
                analysis_name=AnalysisType.RGYR.value,
                analysis_type=AnalysisType.RGYR,
                preprocessing_mode=PreprocessingMode.AS_IS,
            )
            is None
        )

    def test_requires_topology_for_energies_in_as_is_mode(self, tmp_path: Path) -> None:
        """As-is mode should still require topology for analyses that need it."""
        with pytest.raises(BadRequest):
            validate_analysis_topology_path(
                topology_file=None,
                experiment_dir=tmp_path,
                analysis_name=AnalysisType.ENERGIES.value,
                analysis_type=AnalysisType.ENERGIES,
                preprocessing_mode=PreprocessingMode.AS_IS,
            )

    def test_requires_tpr_for_preprocessing_mode(self, tmp_path: Path) -> None:
        """Image-based preprocessing should reject non-TPR topology files."""
        topology = tmp_path / "system.top"
        topology.write_text("[ defaults ]\n", encoding="ascii")

        with pytest.raises(BadRequest):
            validate_analysis_topology_path(
                topology_file=topology.name,
                experiment_dir=tmp_path,
                analysis_name=AnalysisType.RGYR.value,
                analysis_type=AnalysisType.RGYR,
                preprocessing_mode=PreprocessingMode.IMAGE,
            )

    def test_accepts_top_for_as_is_mode(self, tmp_path: Path) -> None:
        """As-is mode should accept supported non-TPR topology files."""
        topology = tmp_path / "system.top"
        topology.write_text("[ defaults ]\n", encoding="ascii")

        assert (
            validate_analysis_topology_path(
                topology_file=topology.name,
                experiment_dir=tmp_path,
                analysis_name=AnalysisType.ENERGIES.value,
                analysis_type=AnalysisType.ENERGIES,
                preprocessing_mode=PreprocessingMode.AS_IS,
            )
            == topology
        )


class TestCheckPositiveInt:
    """Tests for the check_positive_int function."""

    def test_accepts_valid_positive_integer(self) -> None:
        """String representing a positive integer should be accepted."""
        check_positive_int("42")  # Should not raise

    def test_rejects_non_digit_string(self) -> None:
        """Non-numeric string should be rejected."""
        with pytest.raises(BadRequest):
            check_positive_int("abc")

    def test_rejects_zero(self) -> None:
        """Zero should be rejected as it is not a positive integer."""
        with pytest.raises(BadRequest):
            check_positive_int("0")

    def test_rejects_negative_string(self) -> None:
        """Negative number string should be rejected."""
        # isdigit() returns False for negative numbers
        with pytest.raises(BadRequest):
            check_positive_int("-1")

    def test_accepts_value_within_max(self) -> None:
        """Value below the maximum should be accepted."""
        check_positive_int("10", max_value=100)  # Should not raise

    def test_rejects_value_exceeding_max(self) -> None:
        """Value exceeding the maximum should be rejected."""
        with pytest.raises(BadRequest):
            check_positive_int("101", max_value=100)

    def test_accepts_value_equal_to_max(self) -> None:
        """Value equal to the maximum should be accepted."""
        check_positive_int("100", max_value=100)  # Should not raise

    def test_uses_param_name_in_error_message(self) -> None:
        """Error message should include the param_name when provided."""
        with pytest.raises(BadRequest, match="nsteps"):
            check_positive_int("abc", param_name="nsteps")


class TestValidateGitUrl:
    """Tests for the validate_git_url function."""

    def test_accepts_https_github_url(self) -> None:
        """Valid HTTPS GitHub URL should be accepted."""
        validate_git_url("https://github.com/owner/repo.git")  # Should not raise

    def test_accepts_https_gitlab_url(self) -> None:
        """Valid HTTPS GitLab URL should be accepted."""
        validate_git_url("https://gitlab.com/owner/repo.git")  # Should not raise

    def test_accepts_ssh_url(self) -> None:
        """Valid SSH git URL should be accepted."""
        validate_git_url("git@github.com:owner/repo.git")  # Should not raise

    def test_accepts_http_url(self) -> None:
        """HTTP URL should be accepted."""
        validate_git_url("http://github.com/owner/repo.git")  # Should not raise

    def test_rejects_empty_url(self) -> None:
        """Empty URL should be rejected."""
        with pytest.raises(BadRequest):
            validate_git_url("")

    def test_rejects_whitespace_only(self) -> None:
        """Whitespace-only URL should be rejected."""
        with pytest.raises(BadRequest):
            validate_git_url("   ")

    def test_rejects_option_injection(self) -> None:
        """URL starting with a dash should be rejected to prevent option injection."""
        with pytest.raises(BadRequest):
            validate_git_url("--upload-pack=malicious")

    def test_rejects_local_absolute_path(self) -> None:
        """Local absolute path should be rejected."""
        with pytest.raises(BadRequest):
            validate_git_url("/etc/passwd")

    def test_rejects_local_relative_path(self) -> None:
        """Local relative path should be rejected."""
        with pytest.raises(BadRequest):
            validate_git_url("./local/repo")

    def test_rejects_file_protocol(self) -> None:
        """file:// URL should be rejected."""
        with pytest.raises(BadRequest):
            validate_git_url("file:///etc/passwd")

    def test_rejects_url_with_credentials(self) -> None:
        """URL with embedded credentials should be rejected."""
        with pytest.raises(BadRequest):
            validate_git_url("https://user:password@github.com/owner/repo.git")

    def test_rejects_url_with_username_only(self) -> None:
        """URL with embedded username should be rejected."""
        with pytest.raises(BadRequest):
            validate_git_url("https://user@github.com/owner/repo.git")

    def test_rejects_ftp_protocol(self) -> None:
        """Unsupported protocol ftp:// should be rejected."""
        with pytest.raises(BadRequest):
            validate_git_url("ftp://server.com/repo.git")
