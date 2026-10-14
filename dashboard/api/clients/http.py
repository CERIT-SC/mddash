"""Process-wide async HTTP client shared by all upstream clients."""

import httpx

_client: httpx.AsyncClient | None = None


def client() -> httpx.AsyncClient:
    """Return the shared client; created lazily so importing a client module stays side-effect free."""
    global _client  # ruff:ignore[global-statement]
    if _client is None or _client.is_closed:
        # Per-call timeouts are explicit; this default only guards calls that forget one.
        _client = httpx.AsyncClient(timeout=30)
    return _client


async def aclose() -> None:
    """Close the shared client (application shutdown)."""
    global _client  # ruff:ignore[global-statement]
    if _client is not None:
        await _client.aclose()
        _client = None


def detail_of(response: httpx.Response) -> str:
    """Best-effort `detail` of an upstream error response."""
    try:
        body = response.json()
    except ValueError:
        return response.text or f"HTTP {response.status_code}"
    if isinstance(body, dict) and "detail" in body:
        return str(body["detail"])
    return response.text or f"HTTP {response.status_code}"


def raise_for_status(response: httpx.Response) -> None:
    """
    Raise `httpx.HTTPStatusError` carrying the upstream `detail` as its message.

    Raises:
        httpx.HTTPStatusError: If the response is not successful.
    """
    if response.is_success:
        return
    raise httpx.HTTPStatusError(detail_of(response), request=response.request, response=response)
