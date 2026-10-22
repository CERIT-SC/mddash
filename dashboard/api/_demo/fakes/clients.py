"""The client bundle the demo builds the real app with."""

import httpx
from clients import Clients
from clients.git import GitClient
from clients.http import DEFAULT_TIMEOUT

from ..state import E2E
from .git import OfflineGitClient
from .http import register_upstreams
from .k8s import DemoK8sClient
from .router import CallbackRouter
from .tuner import DemoTunerClient


def demo_clients() -> Clients:
    """Production client classes over fake upstreams; Kubernetes, tuner trial logs, and E2E git are replaced."""
    router = CallbackRouter()
    register_upstreams(router)
    http = httpx.AsyncClient(transport=router.transport(), timeout=DEFAULT_TIMEOUT)
    return Clients.create(
        http=http,
        k8s=DemoK8sClient(),
        tuner=DemoTunerClient(http),
        git=OfflineGitClient() if E2E else GitClient(),
    )
