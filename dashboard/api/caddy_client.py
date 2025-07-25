import json
import uuid
import requests
import logging
from requests.exceptions import RequestException


logger = logging.getLogger(__name__)
CADDY_ADMIN_API_URL = "http://localhost:2019"


def add_proxy_route(path: str, upstream: str, route_id: str | None = None) -> str | None:
    """
    Adds a new proxy route for notebook access in the current Caddy configuration.
    Inserts the route before the general dash routes to avoid conflicts with React Router.

    :param path: The path to match for the route (e.g., "/user/admin/dash/notebook/experiment1")
    :param upstream: The address of the server to proxy to (e.g., "localhost:8081")
    :param route_id: Optional. A specific ID for the route. If None, a UUID will be generated.
    :return: The ID of the added route if successful, None otherwise.
    """
    if route_id is None:
        route_id = f"route-{uuid.uuid4()}"

    path = path.rstrip("/")

    new_route_config = {
        "@id": route_id,
        "group": "group4",
        "handle": [
            {
                "handler": "subroute",
                "routes": [
                    {
                        "handle": [
                            {
                                "handler": "reverse_proxy",
                                "upstreams": [
                                    {"dial": upstream}
                                ]
                            }
                        ]
                    }
                ]
            }
        ],
        "match": [
            {
                "path_regexp": {
                    "name": f"{route_id.replace('-', '_')}",
                    "pattern": f"^{path}.*$"
                }
            }
        ]
    }

    # Get current configuration and modify it
    try:
        # Get current config
        config_response = requests.get(f"{CADDY_ADMIN_API_URL}/config/")
        config_response.raise_for_status()
        config = config_response.json()

        # Get current routes
        current_routes = config["apps"]["http"]["servers"]["srv0"]["routes"]

        # Find the dash route (the one with pattern matching /user/admin/dash/.*)
        dash_route_index = None
        for i, route in enumerate(current_routes):
            if "match" in route:
                for match in route["match"]:
                    if "path_regexp" in match:
                        if match["path_regexp"].get("name") == "dash_routes":
                            dash_route_index = i
                            break
                if dash_route_index is not None:
                    break

        # Insert before the dash route, or at position 2 if not found
        insert_position = dash_route_index if dash_route_index is not None else 2
        current_routes.insert(insert_position, new_route_config)

        # Update the config
        config["apps"]["http"]["servers"]["srv0"]["routes"] = current_routes

        # Load the updated config
        headers = {"Content-Type": "application/json"}
        load_response = requests.post(f"{CADDY_ADMIN_API_URL}/load", headers=headers, data=json.dumps(config))
        load_response.raise_for_status()
        return route_id
    except RequestException as e:
        logger.error(f"Error when adding route '{route_id}' to Caddy:", exc_info=True)
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
