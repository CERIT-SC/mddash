"""
Demo mocking infrastructure.

Provides unified mock installation for all external services.
Uses `responses` library for HTTP mocking and module mutation for Kubernetes.
"""

import logging

import responses

logger = logging.getLogger(__name__)  # noqa: RUF067

# Global flag to prevent double installation
_mocks_installed = False  # noqa: RUF067


def install_all_mocks() -> None:  # noqa: RUF067
    """
    Install all demo mocks for external services.

    This function sets up HTTP response mocking via the `responses` library
    and Kubernetes client mocking via module mutation.

    Uses the global `responses.mock` singleton so it works with all requests.
    Must be called before importing any modules that make HTTP requests.
    """
    global _mocks_installed  # noqa: PLW0603

    if _mocks_installed:
        logger.debug("Mocks already installed, skipping")
        return

    from .http import install_http_mocks  # noqa: PLC0415
    from .k8s import install_k8s_mocks  # noqa: PLC0415
    from .tuner_logs import install_tuner_log_mocks  # noqa: PLC0415

    # Install HTTP mocks on the global responses.mock singleton
    install_http_mocks(responses.mock)

    # Activate the global mock - this intercepts all requests
    responses.start()

    # Install K8s mocks (module mutation for kubernetes library)
    install_k8s_mocks()

    # Install tuner log mocks (module mutation for trial stdout/stderr)
    install_tuner_log_mocks()

    _mocks_installed = True
    logger.info("All demo mocks installed")


def stop_mocks() -> None:  # noqa: RUF067
    """Stop HTTP mocking (call on shutdown)."""
    global _mocks_installed  # noqa: PLW0603
    if _mocks_installed:
        responses.stop()
        responses.reset()
        _mocks_installed = False


__all__ = ["install_all_mocks"]
