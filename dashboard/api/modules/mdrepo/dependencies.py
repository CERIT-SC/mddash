"""The request's MDRepo token manager (tokens live in the signed session cookie)."""

from typing import Annotated

from core.dependencies import ClientsDep
from fastapi import Depends, Request

from modules.mdrepo.tokens import MDRepoTokenManager


def get_tokens(request: Request, clients: ClientsDep) -> MDRepoTokenManager:
    """Token manager bound to the request session."""
    return MDRepoTokenManager(request.session, clients.mdrepo)


TokensDep = Annotated[MDRepoTokenManager, Depends(get_tokens)]
