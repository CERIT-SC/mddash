#!/usr/bin/env python3
"""Start a JupyterHub singleuser server with JWT token authentication. Manual test script for the EGI authenticator JWT flow."""

import os

import requests


def start_server():
    token = os.getenv("TOKEN")
    if not token:
        print("Error: TOKEN environment variable missing.")
        return

    base_url = "https://mddash-edc.dyn.cloud.e-infra.cz"
    login_url = f"{base_url}/hub/jwt_login"
    # Server name is empty for the default server, or a named server.
    server_name = ""
    server_url = f"{base_url}/hub/api/users/ljocha/servers/{server_name}"

    # Use a session to manage cookies, including path-based cookies like _xsrf.
    session = requests.Session()

    print("JWT login.")
    login_resp = session.get(login_url, headers={"Authorization": f"bearer {token}"})

    if login_resp.status_code != 200:
        print(f"Login failed: {login_resp.text}")
        return

    xsrf_token = session.cookies.get("_xsrf")

    if not xsrf_token:
        print("Error: No _xsrf cookie returned by the server.")
        return

    print("Login successful.")

    print("Priming session.")

    # Load the home page so the XSRF cookie is set for the /hub/ path.
    session.get(f"{base_url}/hub/home", headers={"Authorization": f"token {token}"})
    xsrf_token = session.cookies.get("_xsrf")

    session.get(f"{base_url}/hub/api/user", headers={"Authorization": f"token {token}"})

    print("Starting server.")

    post_resp = session.post(
        server_url,
        headers={
            "Authorization": f"token {token}",
            "X-XSRFToken": xsrf_token,
            "Content-Type": "application/json",
            "Referer": f"{base_url}/hub/home",
        },
        json={"_xsrf": xsrf_token},
    )

    print(f"Status: {post_resp.status_code}")
    print(f"Body: {post_resp.text}")


if __name__ == "__main__":
    start_server()
