"""The bundle of every upstream client the app is built with."""

from dataclasses import dataclass
from typing import Self

import httpx

from clients.caddy import CaddyClient
from clients.git import GitClient
from clients.http import new_client
from clients.k8s import K8sClient
from clients.mdposit import MDPositClient
from clients.mdrepo import MDRepoClient
from clients.mdrun import MDRunClient
from clients.metadump import MetadumpClient
from clients.tuner import TunerClient


@dataclass(frozen=True, kw_only=True)
class Clients:
    """Every upstream the API talks to."""

    http: httpx.AsyncClient
    k8s: K8sClient
    git: GitClient
    mdrun: MDRunClient
    tuner: TunerClient
    mdrepo: MDRepoClient
    mdposit: MDPositClient
    metadump: MetadumpClient
    caddy: CaddyClient

    @classmethod
    def create(
        cls,
        *,
        http: httpx.AsyncClient | None = None,
        k8s: K8sClient | None = None,
        git: GitClient | None = None,
        mdrun: MDRunClient | None = None,
        tuner: TunerClient | None = None,
        mdrepo: MDRepoClient | None = None,
        mdposit: MDPositClient | None = None,
        metadump: MetadumpClient | None = None,
        caddy: CaddyClient | None = None,
    ) -> Self:
        """Production clients sharing one HTTP connection pool; passed clients replace individual ones."""
        http = http or new_client()
        return cls(
            http=http,
            k8s=k8s or K8sClient(),
            git=git or GitClient(),
            mdrun=mdrun or MDRunClient(http),
            tuner=tuner or TunerClient(http),
            mdrepo=mdrepo or MDRepoClient(http),
            mdposit=mdposit or MDPositClient(http),
            metadump=metadump or MetadumpClient(http),
            caddy=caddy or CaddyClient(http),
        )

    async def aclose(self) -> None:
        """Close the connection pools (application shutdown); one failing close never skips the other."""
        try:
            await self.http.aclose()
        finally:
            await self.k8s.aclose()


__all__ = ["Clients"]
