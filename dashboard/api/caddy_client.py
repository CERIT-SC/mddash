import json
import uuid
import requests
from requests.exceptions import RequestException

from config import PREFIX


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

    # Ensure the path has /* at the end to catch all subpaths
    if not path.endswith("/*"):
        path = path.rstrip("/") + "/*"

    new_route_config = {
        "@id": route_id,
        "match": [
            {"path": [path]}
        ],
        "handle": [
            {
                "handler": "rewrite",
                "uri": f"{PREFIX}{{http.request.uri}}"
            },
            {
                "handler": "reverse_proxy",
                "upstreams": [
                    {"dial": upstream}
                ]
            }
        ]
    }

    # Insert the route at position 2 (after API routes and dash redirect, before general dash routes)
    # This ensures notebook routes are matched before React Router catches them
    url = f"{CADDY_ADMIN_API_URL}/config/apps/http/servers/srv0/routes/@2"
    
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
    url = f"{CADDY_ADMIN_API_URL}/id/{route_id}"
    
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
        path="/user/admin/dash/notebook/experiment1",
        upstream="localhost:8081"
    )

    print(f"Route added successfully with ID: {success}" if success else "Failed to add route.")
