"""Shared authentication utilities."""

import secrets
from typing import Annotated

from fastapi import Depends, HTTPException
from fastapi.security import HTTPBasic, HTTPBasicCredentials

from api.config import TUNER_PASSWORD, TUNER_USER

security = HTTPBasic()


def verify_credentials(credentials: Annotated[HTTPBasicCredentials, Depends(security)]) -> None:
    """
    Verify HTTP Basic Auth credentials.

    Raises:
        HTTPException: 401 if credentials are invalid.
    """
    if not (
        secrets.compare_digest(credentials.username, TUNER_USER)
        and secrets.compare_digest(credentials.password, TUNER_PASSWORD)
    ):
        raise HTTPException(status_code=401, detail="Unauthorized", headers={"WWW-Authenticate": "Basic"})
