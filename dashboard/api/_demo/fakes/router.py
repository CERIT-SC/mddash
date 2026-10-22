"""`responses`-style callback registration served as an httpx transport (the API's HTTP client uses it)."""

import re
from collections.abc import Callable
from dataclasses import dataclass

import httpx


@dataclass(frozen=True)
class MockRequest:
    """The request fields demo callbacks read."""

    method: str
    url: str
    headers: httpx.Headers
    body: bytes


Callback = Callable[[MockRequest], tuple[int, dict[str, str], str | bytes]]


class CallbackRouter:
    """
    First registered match answers; no match fails like an unreachable host.

    String URLs match the request URL without its query string; patterns match its start.
    """

    def __init__(self) -> None:
        """Create a router without routes."""
        self._callbacks: list[tuple[str, str | re.Pattern[str], Callback]] = []

    def add_callback(self, method: str, url: str | re.Pattern[str], callback: Callback) -> None:
        """Answer `method url` requests with `callback`."""
        self._callbacks.append((method.upper(), url, callback))

    def transport(self) -> httpx.MockTransport:
        """Transport answering every request from the registered callbacks."""
        return httpx.MockTransport(self._dispatch)

    def _dispatch(self, request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        for method, pattern, callback in self._callbacks:
            if method != request.method:
                continue
            if isinstance(pattern, str) and pattern != url.split("?", 1)[0]:
                continue
            if isinstance(pattern, re.Pattern) and not pattern.match(url):
                continue
            status, headers, body = callback(MockRequest(request.method, url, request.headers, request.content))
            content = body if isinstance(body, bytes) else body.encode()
            return httpx.Response(status, headers=headers, content=content)
        raise httpx.ConnectError(f"Demo mock: no route for {request.method} {url}", request=request)
