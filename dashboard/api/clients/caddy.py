import json
import logging
import uuid

import requests
from requests.exceptions import RequestException

logger = logging.getLogger(__name__)
CADDY_ADMIN_API_URL = "http://localhost:2019"


def add_proxy_route(path: str, upstream: str, route_id: str | None = None) -> str | None:
    """
    Add a new proxy route inside the @protected (authenticated) Caddy route group.

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
        # Load current config
        resp = requests.get(f"{CADDY_ADMIN_API_URL}/config/", timeout=5)
        resp.raise_for_status()
        config = resp.json()

        routes = config["apps"]["http"]["servers"]["srv0"]["routes"]

        # Find dash route index
        dash_index = next(
            (
                i
                for i, r in enumerate(routes)
                if any(m.get("path_regexp", {}).get("name") == "dash_routes" for m in r.get("match", []))
            ),
            3,
        )

        # Insert new route
        routes.insert(dash_index, new_route)

        # Update Caddy config
        headers = {"Content-Type": "application/json"}
        load_resp = requests.post(f"{CADDY_ADMIN_API_URL}/load", headers=headers, data=json.dumps(config), timeout=5)
        load_resp.raise_for_status()
        return route_id

    except requests.RequestException:
        logger.exception(f"Error adding route '{route_id}' to Caddy")
        return None


def remove_route(route_id: str) -> bool:
    """
    Remove a route from the Caddy configuration using its ID.

    Args:
        route_id: The ID of the route to remove.

    Returns:
        True if the route was removed successfully, False otherwise.
    """
    url = f"{CADDY_ADMIN_API_URL}/id/{route_id}"

    try:
        response = requests.delete(url, timeout=5)
        response.raise_for_status()
        return True
    except RequestException:
        logger.exception(f"Error when removing route '{route_id}' from Caddy")
        return False
