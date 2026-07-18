import ipaddress
import re
import socket
from pathlib import Path
from urllib.parse import ParseResult, urlparse

from enums import AnalysisType, PreprocessingMode
from werkzeug.exceptions import BadRequest, Forbidden

AS_IS_TOPOLOGY_SUFFIXES = {".tpr", ".top", ".prmtop", ".psf"}
PREPROCESSING_TOPOLOGY_SUFFIX = ".tpr"
TOPOLOGY_REQUIRED_ANALYSES = {AnalysisType.ENERGIES}


def check_experiment_id(experiment_id: str) -> None:
    """
    Validate that an experiment ID is a 5-character lowercase string.

    Args:
        experiment_id: The experiment ID to validate.

    Raises:
        BadRequest: If the ID format is invalid.
    """
    if not experiment_id or not re.match(r"^[a-z]{5}$", experiment_id):
        raise BadRequest("Invalid experiment ID format.")


def check_filename(filename: str, allowed_extensions: list[str] | None = None) -> None:
    """
    Validate a filename for security and optional extension restrictions.

    Args:
        filename: The filename to validate.
        allowed_extensions: Optional list of allowed file extensions (without dots).

    Raises:
        BadRequest: If the filename is invalid or extension not allowed.
    """
    if not filename:
        raise BadRequest("Filename cannot be empty.")

    if ".." in filename or "/" in filename or "\\" in filename:
        raise BadRequest("Invalid filename: path traversal not allowed.")

    if filename.startswith(".") or filename.startswith("~"):
        raise BadRequest("Invalid filename: hidden files not allowed.")

    if "\0" in filename:
        raise BadRequest("Invalid filename: null bytes not allowed.")

    if allowed_extensions:
        file_ext = Path(filename).suffix.lstrip(".").lower()
        if not file_ext or file_ext not in allowed_extensions:
            raise BadRequest(f"Invalid file extension. Allowed: {', '.join(allowed_extensions)}")


def check_path(path: str, base_dir: Path) -> None:
    """
    Validate a path is safe and within the allowed base directory.

    Args:
        path: The relative path to validate.
        base_dir: The base directory the path must stay within.

    Raises:
        BadRequest: If the path is invalid.
        Forbidden: If path traversal is detected.
    """
    if not path:
        raise BadRequest("Path cannot be empty.")

    if "\0" in path:
        raise BadRequest("Invalid path: null bytes not allowed.")

    try:
        full_path = (base_dir / path).resolve()
        base_resolved = base_dir.resolve()

        if not str(full_path).startswith(str(base_resolved)):
            raise Forbidden("Path traversal not allowed.")
    except (ValueError, OSError):
        raise BadRequest("Invalid path.")


def validate_analysis_structure_path(
    structure_file: str | None,
    topology_file: str | None,
    experiment_dir: Path,
) -> Path | None:
    """
    Validate that at least one of structure or topology is provided.

    Returns:
        Validated structure path, or None when structure is absent.

    Raises:
        BadRequest: If neither structure nor topology is provided.
    """
    if not structure_file and not topology_file:
        raise BadRequest("Either a structure file or a topology file is required for analysis.")
    if not structure_file:
        return None
    check_path(structure_file, experiment_dir)
    structure_path = Path(structure_file)
    if not (experiment_dir / structure_path).is_file():
        raise BadRequest(f"Structure file {structure_path.as_posix()} does not exist.")
    return structure_path


def validate_analysis_topology_path(
    topology_file: str | None,
    experiment_dir: Path,
    analysis_name: str,
    analysis_type: AnalysisType,
    preprocessing_mode: PreprocessingMode,
) -> Path | None:
    """
    Validate an optional topology file against the selected analysis mode.

    Returns:
        The validated topology path, or None when no topology is required.

    Raises:
        BadRequest: If the topology is missing, invalid, unsupported, or outside the allowed directory.
    """
    requires_topology = analysis_type in TOPOLOGY_REQUIRED_ANALYSES
    requires_preprocessing_topology = preprocessing_mode in {PreprocessingMode.IMAGE, PreprocessingMode.IMAGE_FIT}

    if not topology_file and requires_preprocessing_topology:
        raise BadRequest("A simulation TPR file is required when trajectory preprocessing is enabled.")
    if not topology_file and requires_topology:
        raise BadRequest(f"Analysis '{analysis_name}' requires a topology file (.tpr, .top, .prmtop, .psf).")
    if not topology_file:
        return None

    check_path(topology_file, experiment_dir)
    topology_path = Path(topology_file)
    suffix = topology_path.suffix.lower()

    if requires_preprocessing_topology and suffix != PREPROCESSING_TOPOLOGY_SUFFIX:
        raise BadRequest("Trajectory preprocessing requires a simulation TPR file (.tpr).")
    if not requires_preprocessing_topology and suffix not in AS_IS_TOPOLOGY_SUFFIXES:
        raise BadRequest("Topology files must use one of: .tpr, .top, .prmtop, .psf.")
    if not (experiment_dir / topology_path).is_file():
        raise BadRequest(f"Topology file {topology_path.as_posix()} does not exist.")

    return topology_path


def check_log_type(log_type: str) -> None:
    """
    Validate that log_type is one of the allowed values.

    Args:
        log_type: The log type to validate ('gmx', 'stdout', or 'stderr').

    Raises:
        BadRequest: If the log type is invalid.
    """
    if log_type not in {"gmx", "stdout", "stderr"}:
        raise BadRequest("Invalid log type. Use 'gmx', 'stdout', or 'stderr'.")


def check_positive_int(value: str, param_name: str = "value", max_value: int | None = None) -> None:
    """
    Validate that a string represents a positive integer within bounds.

    Args:
        value: The string value to validate.
        param_name: Name of the parameter for error messages.
        max_value: Optional maximum allowed value.

    Raises:
        BadRequest: If the value is not a valid positive integer or exceeds max.
    """
    if not value.isdigit():
        raise BadRequest(f"{param_name} must be a positive integer.")

    int_value = int(value)
    if int_value <= 0:
        raise BadRequest(f"{param_name} must be greater than 0.")

    if max_value and int_value > max_value:
        raise BadRequest(f"{param_name} must not exceed {max_value}.")


def validate_git_url(git_url: str) -> None:
    """
    Validate git URL for safety.

    Rejects unsafe URL patterns: credentials, local paths, file://, option injection.

    Raises:
        BadRequest: If URL is invalid or unsafe.
    """
    if not git_url or not git_url.strip():
        raise BadRequest("Git URL cannot be empty.")

    url = git_url.strip()

    # Reject option injection, local paths, file:// URLs
    if url.startswith("-") or url.startswith("/") or url.startswith("."):
        raise BadRequest("Invalid git URL format.")
    if url.lower().startswith("file://"):
        raise BadRequest("file:// URLs are not allowed.")

    # SSH format: git@host:owner/repo.git - valid
    if url.startswith("git@") and ":" in url:
        return

    _assert_http_url_safe(
        urlparse(url),
        allowed_schemes={"http", "https"},
        scheme_msg="Only http://, https://, or git@ URLs are allowed.",
        missing_host_msg="Invalid git URL: missing host.",
    )


def _assert_http_url_safe(
    parsed: ParseResult,
    *,
    allowed_schemes: set[str],
    scheme_msg: str,
    missing_host_msg: str,
) -> None:
    """
    Shared HTTP(S) safety core: scheme allow-list, no embedded credentials, host present.

    Raises:
        BadRequest: If the scheme is unsupported, credentials are embedded, or the host is missing.
    """
    if parsed.scheme not in allowed_schemes:
        raise BadRequest(scheme_msg)
    if parsed.username or parsed.password:
        raise BadRequest("URLs with embedded credentials are not allowed.")
    if not parsed.netloc:
        raise BadRequest(missing_host_msg)


def _is_reserved_ip(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    """
    Check whether an IP is loopback, private, link-local, reserved, multicast, or unspecified.

    Returns:
        True if the IP is internal/reserved and must not be fetched.
    """
    return ip.is_loopback or ip.is_private or ip.is_link_local or ip.is_reserved or ip.is_multicast or ip.is_unspecified


def _getaddrinfo_ips(hostname: str) -> list[str]:
    """
    Resolve hostname to deduplicated literal IP strings via getaddrinfo.

    Returns:
        The deduplicated list of resolved IP strings.

    Raises:
        BadRequest: If the hostname cannot be resolved.
    """
    try:
        infos = socket.getaddrinfo(hostname, None)
    except socket.gaierror as exc:
        raise BadRequest(f"Could not resolve host '{hostname}': {exc}")
    seen: list[str] = []
    for info in infos:
        ip = str(info[4][0])
        if ip not in seen:
            seen.append(ip)
    return seen


def validate_http_url(url: str) -> str:
    """
    Validate an HTTP(S) URL for server-side fetching.

    Rejects non-http(s) schemes, embedded credentials, and missing hosts.
    Reserved-IP checks are handled by :func:`validate_fetch_target`.

    Returns:
        The validated, normalized URL.

    Raises:
        BadRequest: If the URL is empty, has an unsupported scheme, embeds credentials, or is missing a host.
    """
    if not url or not url.strip():
        raise BadRequest("URL cannot be empty.")

    parsed = urlparse(url.strip())
    _assert_http_url_safe(
        parsed,
        allowed_schemes={"http", "https"},
        scheme_msg="Only http:// and https:// URLs are allowed.",
        missing_host_msg="Invalid URL: missing host.",
    )
    return parsed.geturl()


def validate_fetch_target(url: str) -> None:
    """
    Reject URLs whose host is or resolves to a reserved/internal IP (SSRF guard).

    Literal IPs are checked directly; hostnames are resolved via
    :func:`_getaddrinfo_ips` and every resolved IP is checked. Targets are
    matched by resolved address rather than an enumerated hostname list.

    Raises:
        BadRequest: If the host is or resolves to a reserved/internal IP.
    """
    hostname = urlparse(url).hostname or ""
    try:
        ips: list[ipaddress.IPv4Address | ipaddress.IPv6Address] = [ipaddress.ip_address(hostname)]
    except ValueError:
        ips = [ipaddress.ip_address(ip) for ip in _getaddrinfo_ips(hostname)]

    if any(_is_reserved_ip(ip) for ip in ips):
        raise BadRequest("Internal or reserved host targets are not allowed.")
