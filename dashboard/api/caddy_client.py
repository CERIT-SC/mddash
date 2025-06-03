import json
import uuid
import requests
from requests.exceptions import RequestException

from config import PREFIX


CADDY_ADMIN_API_URL = "http://localhost:2019"


def add_proxy_route(path: str, upstream: str, route_id: str = None) -> str:
    """
    Adds a new WebSocket proxy route inside the first handle_path block of the first HTTP server in Caddy.
    Assigns a unique ID to the route for easier deletion.

    :param relative_path_match: The path to match for the WebSocket route.
    :param upstream_address: The address of the WebSocket server to proxy to.
    :param route_id: Optional. A specific ID for the route. If None, a UUID will be generated.
    :return: The ID of the added route if successful, None otherwise.
    """
    if route_id is None:
        route_id = f"route-{uuid.uuid4()}" # Generate a unique ID

    new_route_config = {
        "@id": route_id,
        "match": [
            {"path": [path]}
        ],
        "handle": [
            {
                "handler": "subroute",
                "routes": [
                    {
                        "handle": [
                            # prepend the striped prefix to the request URI
                            {
                                "handler": "rewrite",
                                "uri": f"{PREFIX}{{http.request.uri}}"
                            },
                            # proxy the request to the upstream server
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
        ]
    }

    # NOTE: This kinda relies on the Caddyfile config
    # Assumes:
    # - srv0 is the first server
    # - The handle_path block is the first route in srv0 (index 0)
    # - The handle_path's internal subroute handler is the first handler (index 0)
    url = f"{CADDY_ADMIN_API_URL}/config/apps/http/servers/srv0/routes/0/handle/0/routes/"
    
    headers = {"Content-Type": "application/json"}

    try:
        response = requests.post(url, headers=headers, data=json.dumps(new_route_config))
        print(f"Caddy API Response Status (Add Route {route_id}): {response.status_code}")
        print(f"Caddy API Response Body (Add Route {route_id}): {response.text}")
        response.raise_for_status()
        return route_id
    except RequestException as e:
        print(f"Error connecting to Caddy Admin API or making request (Add Route {route_id}): {e}")
        return None


def remove_route(route_id: str) -> bool:
    """
    Removes a route from the Caddy configuration using its ID.

    :param route_id: The ID of the route to remove.
    :return: True if the route was removed successfully, False otherwise.
    """
    url = f"{CADDY_ADMIN_API_URL}/config/apps/http/servers/srv0/routes/0/handle/0/routes/id/{route_id}"
    
    try:
        response = requests.delete(url)
        print(f"Caddy API Response Status (Remove Route {route_id}): {response.status_code}")
        print(f"Caddy API Response Body (Remove Route {route_id}): {response.text}")
        response.raise_for_status()
        return True
    except RequestException as e:
        print(f"Error connecting to Caddy Admin API or making request (Remove Route {route_id}): {e}")
        return False


# DEMO
if __name__ == "__main__":

    success = add_proxy_route(
        path="/my_endpoint/*",
        upstream="localhost:8081"
    )

    print(f"Route added successfully with ID: {success}" if success else "Failed to add route.")
