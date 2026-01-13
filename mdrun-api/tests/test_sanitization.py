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
        "dir/evil.tpr",
        "evil\\path.tpr",
        "evil.tpr;rm -rf /",
        "evil",
        "evil.txt",
        "",
    ],
)
def test_sanitize_tpr_name_rejects_bad_values(tpr_name: str) -> None:
    """Reject TPR names that look like paths or contain shell metacharacters."""
    with pytest.raises(ValidationError):
        sanitize_tpr_name(tpr_name)


def test_sanitize_tpr_name_accepts_normal_value() -> None:
    """Accept a simple TPR filename ending with .tpr."""
    assert sanitize_tpr_name("simulation.tpr") == "simulation.tpr"


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
        "-deffnm hacked",
    ],
)
def test_sanitize_extra_args_rejects_injection(extra_args: str) -> None:
    """Reject extra_args that include shell metacharacters or forbidden flags."""
    with pytest.raises(ValidationError):
        sanitize_extra_args(extra_args)


def test_sanitize_extra_args_normalizes_whitespace_and_quotes() -> None:
    """Normalize spacing and remove redundant quotes from extra_args."""
    assert sanitize_extra_args("  -nsteps   1000  ") == "-nsteps 1000"
    assert sanitize_extra_args("-nsteps '1000'") == "-nsteps 1000"


def test_sanitize_extra_args_allows_empty() -> None:
    """Empty or whitespace-only extra_args should be accepted as empty string."""
    assert sanitize_extra_args("") == ""
    assert sanitize_extra_args("   ") == ""
