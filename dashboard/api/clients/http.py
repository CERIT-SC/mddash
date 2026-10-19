"""Helpers shared by the HTTP upstream clients."""

import httpx

# Per-call timeouts are explicit; this default only guards calls that forget one.
DEFAULT_TIMEOUT = 30


def new_client() -> httpx.AsyncClient:
    """Create the process-wide HTTP client every upstream client shares (one connection pool)."""
    return httpx.AsyncClient(timeout=DEFAULT_TIMEOUT)


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
