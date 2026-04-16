import re
import shlex

from marshmallow import ValidationError

_EXPERIMENT_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")
_TPR_SEGMENT_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,246}$")

# S3 bucket naming is more nuanced, but this is a safe baseline that also
# prevents shell injection via whitespace/metacharacters.
_BUCKET_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9.-]{1,61}[a-z0-9]$")

_EXTRA_ARGS_FORBIDDEN_RE = re.compile(r"[;&|><`]|\$\(|\$\{|\n|\r|\x00")
_EXTRA_ARGS_FORBIDDEN_FLAGS = {"-deffnm"}
MAX_EXTRA_ARGS_TOKENS = 80


def sanitize_experiment_id(experiment_id: str) -> str:
    """
    Validate experiment ID used as a path segment and S3 prefix.

    Returns:
        str: The validated, stripped experiment ID.

    Raises:
        ValidationError: If the experiment ID does not match the required pattern.
    """
    experiment_id = (experiment_id or "").strip()
    if not _EXPERIMENT_ID_RE.fullmatch(experiment_id):
        raise ValidationError("Invalid experiment_id.")
    return experiment_id


def sanitize_tpr_name(tpr_name: str) -> str:
    """
    Validate a TPR relative path (may include subdirectories).

    Returns:
        str: The validated, stripped TPR path.

    Raises:
        ValidationError: If the path is empty, absolute, contains forbidden characters,
            has invalid segments, or does not end with .tpr.
    """
    tpr_name = (tpr_name or "").strip()
    if not tpr_name:
        raise ValidationError("tpr_name cannot be empty.")
    if "\\" in tpr_name or "\0" in tpr_name:
        raise ValidationError("tpr_name contains forbidden characters.")
    if tpr_name.startswith("/"):
        raise ValidationError("tpr_name must be a relative path.")

    segments = tpr_name.split("/")
    for segment in segments:
        if not segment or segment == ".." or not _TPR_SEGMENT_RE.fullmatch(segment):
            raise ValidationError("Invalid tpr_name.")

    if not tpr_name.endswith(".tpr"):
        raise ValidationError("tpr_name must end with .tpr.")
    return tpr_name


def sanitize_bucket_name(bucket_name: str) -> str:
    """
    Validate the S3 bucket name.

    Returns:
        str: The validated, stripped bucket name.

    Raises:
        ValidationError: If the bucket name does not match the required pattern.
    """
    bucket_name = (bucket_name or "").strip()
    if not _BUCKET_NAME_RE.fullmatch(bucket_name):
        raise ValidationError("Invalid bucket_name.")
    return bucket_name


def sanitize_extra_args(extra_args: str) -> str:
    """
    Validate and normalize extra GROMACS mdrun args.

    This is used inside a shell script in the K8s job container, so we block
    shell metacharacters and also forbid overriding critical args.

    Returns:
        str: Canonicalized extra args string, or an empty string if none were provided.

    Raises:
        ValidationError: If the args contain forbidden characters, forbidden flags,
            exceed the token limit, or cannot be parsed by shlex.
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


def _sanitize_filename_with_ext(filename: str, name_field: str, allowed_exts: tuple[str, ...]) -> str:
    """
    Validate a filename with allowed extensions (may include subdirectories).

    Args:
        filename: The filename to validate.
        name_field: Field name for error messages.
        allowed_exts: Tuple of allowed file extensions (with leading dot).

    Returns:
        str: The validated, stripped filename.

    Raises:
        ValidationError: If the filename is invalid.
    """
    filename = (filename or "").strip()
    if not filename:
        raise ValidationError(f"{name_field} cannot be empty.")
    if "\\" in filename or "\0" in filename:
        raise ValidationError(f"{name_field} contains forbidden characters.")
    if filename.startswith("/"):
        raise ValidationError(f"{name_field} must be a relative path.")

    segments = filename.split("/")
    for segment in segments:
        if not segment or segment == ".." or not _TPR_SEGMENT_RE.fullmatch(segment):
            raise ValidationError(f"Invalid {name_field}.")

    if not any(filename.endswith(ext) for ext in allowed_exts):
        exts = ", ".join(allowed_exts)
        raise ValidationError(f"{name_field} must end with one of: {exts}.")
    return filename


def sanitize_prmtop_name(prmtop_name: str) -> str:
    """
    Validate AMBER topology file name (.prmtop or .parm7).

    Returns:
        The validated, stripped filename.
    """
    return _sanitize_filename_with_ext(prmtop_name, "prmtop_name", (".prmtop", ".parm7"))


def sanitize_inpcrd_name(inpcrd_name: str) -> str:
    """
    Validate AMBER coordinate file name (.inpcrd, .rst7, or .nc).

    Returns:
        The validated, stripped filename.
    """
    return _sanitize_filename_with_ext(inpcrd_name, "inpcrd_name", (".inpcrd", ".rst7", ".nc"))


def sanitize_mdin_name(mdin_name: str) -> str:
    """
    Validate AMBER input file name (.mdin or .in).

    Returns:
        The validated, stripped filename.
    """
    return _sanitize_filename_with_ext(mdin_name, "mdin_name", (".mdin", ".in"))
