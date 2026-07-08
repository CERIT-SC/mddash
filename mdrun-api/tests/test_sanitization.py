"""
Unit tests for user-input sanitization.

These tests focus on blocking shell/arg injection since job execution uses `bash -c`.
"""

import pytest
from marshmallow import ValidationError
from sanitization import (
    sanitize_bucket_name,
    sanitize_experiment_id,
    sanitize_extra_args,
    sanitize_tpr_name,
)


@pytest.mark.parametrize(
    "experiment_id",
    [
        "../x",
        "x/../y",
        "x y",
        "x;y",
        "",
        "-starts-with-dash",
        "x" * 100,
    ],
)
def test_sanitize_experiment_id_rejects_bad_values(experiment_id: str) -> None:
    """Reject invalid experiment_id values (path traversal, whitespace, etc.)."""
    with pytest.raises(ValidationError):
        sanitize_experiment_id(experiment_id)


def test_sanitize_experiment_id_accepts_normal_value() -> None:
    """Allow a normal experiment id with underscores and dashes."""
    assert sanitize_experiment_id("exp_123-abc") == "exp_123-abc"


@pytest.mark.parametrize(
    "tpr_name",
    [
        "../evil.tpr",
        "dir/../evil.tpr",
        "/abs/path.tpr",
        "evil\\path.tpr",
        "evil.tpr;rm -rf /",
        "dir//file.tpr",
        ".hidden/file.tpr",
        "evil",
        "evil.txt",
        "",
    ],
)
def test_sanitize_tpr_name_rejects_bad_values(tpr_name: str) -> None:
    """Reject TPR names with traversal, shell metacharacters, or wrong extension."""
    with pytest.raises(ValidationError):
        sanitize_tpr_name(tpr_name)


@pytest.mark.parametrize(
    "tpr_name",
    [
        "simulation.tpr",
        "subdir/simulation.tpr",
        "a/b/c/run.tpr",
    ],
)
def test_sanitize_tpr_name_accepts_valid_values(tpr_name: str) -> None:
    """Accept plain filenames and relative paths ending with .tpr."""
    assert sanitize_tpr_name(tpr_name) == tpr_name


@pytest.mark.parametrize(
    "bucket_name",
    [
        "Test-Bucket",  # uppercase not allowed
        "bucket with spaces",
        "bucket;rm",
        "-bad",
        "bad-",
        "b" * 80,
        "",
    ],
)
def test_sanitize_bucket_name_rejects_bad_values(bucket_name: str) -> None:
    """Reject invalid S3 bucket names (spaces, uppercase, too long, etc.)."""
    with pytest.raises(ValidationError):
        sanitize_bucket_name(bucket_name)


def test_sanitize_bucket_name_accepts_normal_value() -> None:
    """Allow a typical lowercase-dash S3 bucket name."""
    assert sanitize_bucket_name("my-bucket-123") == "my-bucket-123"


@pytest.mark.parametrize(
    "extra_args",
    [
        "-nsteps 1000; rm -rf /",
        "-nsteps 1000 && whoami",
        "$(id)",
        "${HOME}",
        "-nsteps 1000 | cat",
        "-nsteps 1000 > /tmp/x",
        "-nsteps 1000 < /etc/passwd",
        "-nsteps 1000 `id`",
    ],
)
def test_sanitize_extra_args_rejects_injection(extra_args: str) -> None:
    """Reject extra_args that include shell metacharacters (any engine)."""
    with pytest.raises(ValidationError):
        sanitize_extra_args(extra_args, "gmx")
    with pytest.raises(ValidationError):
        sanitize_extra_args(extra_args, "amber")


@pytest.mark.parametrize(
    "extra_args",
    [
        "-deffnm hacked",
        "-s other.tpr",
        "-o /tmp/out.trr",
        "-x /tmp/traj.xtc",
        "-c /tmp/final.gro",
        "-e /tmp/ener.edr",
        "-g /tmp/run.log",
        "-cpo /tmp/state.cpt",
        "-dhdl /tmp/dhdl.xvg",
        "-px /tmp/pullx.xvg",
        "-pf /tmp/pullf.xvg",
        "-mtx /tmp/matrix.mtx",
    ],
)
def test_sanitize_extra_args_rejects_gmx_forbidden_flags(extra_args: str) -> None:
    """Reject GMX flags that redirect outputs or override harness inputs."""
    with pytest.raises(ValidationError):
        sanitize_extra_args(extra_args, "gmx")


@pytest.mark.parametrize(
    "extra_args",
    [
        "-i custom.mdin",
        "-p custom.prmtop",
        "-c custom.rst7",
        "-o /tmp/mdout",
        "-r /tmp/restrt.rst7",
        "-x /tmp/traj.nc",
        "-inf /tmp/mdinfo",
    ],
)
def test_sanitize_extra_args_rejects_amber_forbidden_flags(extra_args: str) -> None:
    """Reject AMBER flags that redirect outputs or override harness inputs."""
    with pytest.raises(ValidationError):
        sanitize_extra_args(extra_args, "amber")


def test_sanitize_extra_args_allows_amber_overwrite_flag() -> None:
    """
    AMBER `-O` (capital) is the boolean overwrite flag and must be allowed.

    Only the lowercase `-o` (mdout output path) is forbidden. This is the key
    reason flag matching is case-sensitive and engine-specific.
    """
    assert sanitize_extra_args("-O -nsteps 1000", "amber") == "-O -nsteps 1000"


def test_sanitize_extra_args_allows_amber_minus_o_for_gmx() -> None:
    """AMBER-only forbidden flags like `-r`/`-inf` are allowed for GMX (not GMX flags)."""
    # GMX doesn't have -r/-inf, so they pass through harmlessly.
    assert sanitize_extra_args("-r 1.0 -inf 100", "gmx") == "-r 1.0 -inf 100"


def test_sanitize_extra_args_allows_legitimate_gmx_args() -> None:
    """Allow genuine GROMACS mdrun tuning flags that don't redirect outputs."""
    assert sanitize_extra_args("-nsteps 1000 -maxh 1.0 -v -resethway", "gmx") == "-nsteps 1000 -maxh 1.0 -v -resethway"


def test_sanitize_extra_args_rejects_unknown_engine() -> None:
    """An unrecognized engine value must raise ValidationError."""
    with pytest.raises(ValidationError):
        sanitize_extra_args("-nsteps 1000", "lammps")


def test_sanitize_extra_args_normalizes_whitespace_and_quotes() -> None:
    """Normalize spacing and remove redundant quotes from extra_args."""
    assert sanitize_extra_args("  -nsteps   1000  ", "gmx") == "-nsteps 1000"
    assert sanitize_extra_args("-nsteps '1000'", "gmx") == "-nsteps 1000"


def test_sanitize_extra_args_allows_empty() -> None:
    """Empty or whitespace-only extra_args should be accepted as empty string."""
    assert not sanitize_extra_args("", "gmx")
    assert not sanitize_extra_args("   ", "amber")
