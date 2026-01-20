import re
import shlex

from marshmallow import ValidationError

_EXPERIMENT_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")
_TPR_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,246}\.tpr$")

# S3 bucket naming is more nuanced, but this is a safe baseline that also
# prevents shell injection via whitespace/metacharacters.
_BUCKET_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9.-]{1,61}[a-z0-9]$")

_EXTRA_ARGS_FORBIDDEN_RE = re.compile(r"[;&|><`]|\$\(|\$\{|\n|\r|\x00")
_EXTRA_ARGS_FORBIDDEN_FLAGS = {"-deffnm"}
MAX_EXTRA_ARGS_TOKENS = 80


def sanitize_experiment_id(experiment_id: str) -> str:
    """Validate experiment ID used as a path segment and S3 prefix."""
    experiment_id = (experiment_id or "").strip()
    if not _EXPERIMENT_ID_RE.fullmatch(experiment_id):
        raise ValidationError("Invalid experiment_id.")
    return experiment_id


def sanitize_tpr_name(tpr_name: str) -> str:
    """Validate the TPR filename (must be a plain filename, not a path)."""
    tpr_name = (tpr_name or "").strip()
    if "/" in tpr_name or "\\" in tpr_name:
        raise ValidationError("tpr_name must be a filename, not a path.")
    if not _TPR_NAME_RE.fullmatch(tpr_name):
        raise ValidationError("Invalid tpr_name (expected something like 'run.tpr').")
    return tpr_name


def sanitize_bucket_name(bucket_name: str) -> str:
    """Validate the S3 bucket name."""
    bucket_name = (bucket_name or "").strip()
    if not _BUCKET_NAME_RE.fullmatch(bucket_name):
        raise ValidationError("Invalid bucket_name.")
    return bucket_name


def sanitize_extra_args(extra_args: str) -> str:
    """
    Validate and normalize extra GROMACS mdrun args.

    This is used inside a shell script in the K8s job container, so we block
    shell metacharacters and also forbid overriding critical args.
    """
    extra_args = (extra_args or "").strip()
    if not extra_args:
        return ""

    if _EXTRA_ARGS_FORBIDDEN_RE.search(extra_args):
        raise ValidationError("extra_args contains forbidden characters.")

    try:
        tokens = shlex.split(extra_args, posix=True)
    except ValueError as e:
        raise ValidationError(f"Invalid extra_args: {e}") from e

    if len(tokens) > MAX_EXTRA_ARGS_TOKENS:
        raise ValidationError("extra_args is too long.")

    lowered = {t.lower() for t in tokens}
    if lowered & _EXTRA_ARGS_FORBIDDEN_FLAGS:
        raise ValidationError("extra_args must not override -deffnm.")

    # Canonicalize spacing/quoting.
    return shlex.join(tokens)
