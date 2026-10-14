import logging
import uuid
from http import HTTPStatus

import httpx

from clients.http import client

logger = logging.getLogger(__name__)
CADDY_ADMIN_API_URL = "http://localhost:2019"


async def add_proxy_route(path: str, upstream: str, route_id: str | None = None) -> str | None:
    """
    Add a proxy route inside the @protected (authenticated) Caddy route group.

    Args:
        path: The path to match for the route (e.g., "/user/admin/dash/notebook/experiment1").
        upstream: The address of the server to proxy to (e.g., "localhost:8081").
        route_id: A specific ID for the route. If None, a UUID will be generated.

    Returns:
        The ID of the added route if successful, None otherwise.
    """
    route_id = route_id or f"route-{uuid.uuid4()}"
    path = path.rstrip("/")

    new_route = {
        "@id": route_id,
        "group": "group4",
        "handle": [{"handler": "reverse_proxy", "upstreams": [{"dial": upstream}]}],
        "match": [{"path_regexp": {"name": route_id.replace("-", "_"), "pattern": f"^{path}.*$"}}],
    }

    try:
        resp = await client().get(f"{CADDY_ADMIN_API_URL}/config/", timeout=5)
        resp.raise_for_status()
        config = resp.json()

        routes = config["apps"]["http"]["servers"]["srv0"]["routes"]

        # Remove stale route with the same ID (e.g. left behind after idle culling)
        routes[:] = [r for r in routes if r.get("@id") != route_id]

        # Find dash route index after filtering so the insert position is correct
        dash_index = next(
            (
                i
                for i, r in enumerate(routes)
                if any(m.get("path_regexp", {}).get("name") == "dash_routes" for m in r.get("match", []))
            ),
            3,
        )
        routes.insert(dash_index, new_route)

        load_resp = await client().post(f"{CADDY_ADMIN_API_URL}/load", json=config, timeout=5)
        load_resp.raise_for_status()
        return route_id

    except httpx.HTTPError:
        logger.exception(f"Error adding route '{route_id}' to Caddy")
        return None


async def remove_route(route_id: str) -> bool:
    """
    Remove a route from the Caddy configuration by ID.

    Returns:
        True if the route was removed (or was already gone), False otherwise.
    """
    try:
        response = await client().delete(f"{CADDY_ADMIN_API_URL}/id/{route_id}", timeout=5)
        if response.status_code == HTTPStatus.NOT_FOUND:
            return True  # Already gone; deletion stays idempotent.
        response.raise_for_status()
        return True
    except httpx.HTTPError:
        logger.exception(f"Error when removing route '{route_id}' from Caddy")
        return False
