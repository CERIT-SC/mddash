"""
Demo mocking infrastructure.

HTTP goes through a respx-backed callback router; Kubernetes, tuner trial logs,
and (E2E) git clones are replaced by module mutation.
"""

import logging

logger = logging.getLogger(__name__)  # ruff:ignore[non-empty-init-module]

# Global flag to prevent double installation
_mocks_installed = False  # ruff:ignore[non-empty-init-module]


def install_all_mocks() -> None:  # ruff:ignore[non-empty-init-module]
    """
    Install all demo mocks for external services.

    Must run before importing any modules that bind the mocked functions.
    """
    global _mocks_installed  # ruff:ignore[global-statement]

    if _mocks_installed:
        logger.debug("Mocks already installed, skipping")
        return

    from .http import install_http_mocks  # ruff:ignore[import-outside-top-level]
    from .k8s import install_k8s_mocks  # ruff:ignore[import-outside-top-level]
    from .router import CallbackRouter  # ruff:ignore[import-outside-top-level]
    from .tuner_logs import install_tuner_log_mocks  # ruff:ignore[import-outside-top-level]

    router = CallbackRouter()
    install_http_mocks(router)
    router.start()

    # Install K8s mocks (module mutation for kubernetes library)
    install_k8s_mocks()

    # Install tuner log mocks (module mutation for trial stdout/stderr)
    install_tuner_log_mocks()

    from ..state import E2E  # ruff:ignore[import-outside-top-level]

    if E2E:
        from .git import install_git_mocks  # ruff:ignore[import-outside-top-level]

        install_git_mocks()

    _mocks_installed = True
    logger.info("All demo mocks installed")


__all__ = ["install_all_mocks"]
