import pytest
from api.utils import AMBER_FORBIDDEN_FLAGS, GMX_FORBIDDEN_FLAGS, sanitize_extra_args


class TestSanitizeExtraArgs:
    def test_empty_string_returns_empty(self) -> None:
        assert sanitize_extra_args("", GMX_FORBIDDEN_FLAGS) == ""

    def test_valid_args_pass_through(self) -> None:
        result = sanitize_extra_args("-ntmpi 2", GMX_FORBIDDEN_FLAGS)
        assert result == "-ntmpi 2"

    def test_forbidden_characters_raise(self) -> None:
        with pytest.raises(ValueError, match="forbidden characters"):
            sanitize_extra_args("-ntmpi 2; rm -rf /", GMX_FORBIDDEN_FLAGS)

    def test_forbidden_gmx_flags_raise(self) -> None:
        with pytest.raises(ValueError, match="critical"):
            sanitize_extra_args("-ntomp 4", GMX_FORBIDDEN_FLAGS)

    def test_forbidden_flag_s_raises(self) -> None:
        with pytest.raises(ValueError, match="critical"):
            sanitize_extra_args("-s other.tpr", GMX_FORBIDDEN_FLAGS)


class TestSanitizeAmberExtraArgs:
    def test_empty_string_returns_empty(self) -> None:
        assert sanitize_extra_args("", AMBER_FORBIDDEN_FLAGS) == ""

    def test_valid_amber_args_pass_through(self) -> None:
        result = sanitize_extra_args("-AllowSmallBox", AMBER_FORBIDDEN_FLAGS)
        assert result == "-AllowSmallBox"

    def test_forbidden_characters_raise(self) -> None:
        with pytest.raises(ValueError, match="forbidden characters"):
            sanitize_extra_args("-AllowSmallBox; rm -rf /", AMBER_FORBIDDEN_FLAGS)

    def test_forbidden_amber_flag_i_raises(self) -> None:
        with pytest.raises(ValueError, match="critical"):
            sanitize_extra_args("-i custom.mdin", AMBER_FORBIDDEN_FLAGS)

    def test_forbidden_amber_flag_p_raises(self) -> None:
        with pytest.raises(ValueError, match="critical"):
            sanitize_extra_args("-p other.prmtop", AMBER_FORBIDDEN_FLAGS)

    def test_forbidden_amber_flag_O_raises(self) -> None:
        with pytest.raises(ValueError, match="critical"):
            sanitize_extra_args("-O", AMBER_FORBIDDEN_FLAGS)

    def test_multiple_valid_args_pass_through(self) -> None:
        result = sanitize_extra_args("-AllowSmallBox -verbose", AMBER_FORBIDDEN_FLAGS)
        assert result == "-AllowSmallBox -verbose"

    def test_equals_syntax_forbidden_flag_raises(self) -> None:
        with pytest.raises(ValueError, match="critical"):
            sanitize_extra_args("-i=custom.mdin", AMBER_FORBIDDEN_FLAGS)
