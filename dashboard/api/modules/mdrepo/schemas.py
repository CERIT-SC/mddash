"""MDRepo authentication schemas."""

from typing import NotRequired, TypedDict

from pydantic import ConfigDict, with_config


@with_config(ConfigDict(extra="forbid"))
class MDRepoStatus(TypedDict):
    """MDRepo authentication status."""

    authenticated: bool
    mdrepo_url: NotRequired[str]
