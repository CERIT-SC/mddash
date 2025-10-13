import json
import uuid
import requests
import logging
from requests.exceptions import RequestException


logger = logging.getLogger(__name__)
CADDY_ADMIN_API_URL = "http://localhost:2019"


def add_proxy_route(path: str, upstream: str, route_id: str | None = None) -> str | None:
    """
    Adds a new proxy route inside the @protected (authenticated) Caddy route group.
    
    :param path: The path to match for the route (e.g., "/user/admin/dash/notebook/experiment1")
    :param upstream: The address of the server to proxy to (e.g., "localhost:8081")
    :param route_id: Optional. A specific ID for the route. If None, a UUID will be generated.
    :return: The ID of the added route if successful, None otherwise.
    """
    if route_id is None:
        route_id = f"route-{uuid.uuid4()}"

    path = path.rstrip("/")

    new_route = {
        "@id": route_id,
        "match": [
            {
                "path_regexp": {
                    "name": route_id.replace("-", "_"),
                    "pattern": f"^{path}.*$"
                }
            }
        ],
        "handle": [
            {
                "handler": "reverse_proxy",
                "upstreams": [{"dial": upstream}]
            }
        ]
    }

    try:
        # Get current config
        config = requests.get(f"{CADDY_ADMIN_API_URL}/config/").json()

        # XXX: This shit is as hardcoded as it can be, but hey it works (until you change the Caddyfile)
        routes = config["apps"]["http"]["servers"]["srv0"]["routes"][0]["handle"][0]["routes"][0]["handle"][1]["routes"]
        routes.insert(0, new_route)  # Insert at the beginning to give it higher priority

        # Overwrite the config
        headers = {"Content-Type": "application/json"}
        requests.post(f"{CADDY_ADMIN_API_URL}/load", headers=headers, data=json.dumps(config)).raise_for_status()

        return route_id

    except Exception:
        logger.exception(f"Failed to add route {route_id}")
        return None


def remove_route(route_id: str) -> bool:
    """
    Removes a route from the Caddy configuration using its ID.

    :param route_id: The ID of the route to remove.
    :return: True if the route was removed successfully, False otherwise.
    """
    url = f"{CADDY_ADMIN_API_URL}/id/{route_id}"

    try:
        response = requests.delete(url)
        response.raise_for_status()
        return True
    except RequestException as e:
        logger.error(f"Error when removing route '{route_id}' from Caddy:", exc_info=True)
        return False
