#!/usr/bin/env python3
"""
Start a JupyterHub singleuser server using JWT token authentication.

A standalone manual test script for exercising the EGI authenticator JWT
callback flow against the MDDash EDC deployment.
"""

import os

import requests


def start_server():
    token = os.getenv("TOKEN")
    if not token:
        print("Error: TOKEN environment variable missing.")
        return

    base_url = "https://mddash-edc.dyn.cloud.e-infra.cz"
    login_url = f"{base_url}/hub/jwt_login"
    # Server name can be empty string for default server, or a named server
    server_name = ""
    server_url = f"{base_url}/hub/api/users/ljocha/servers/{server_name}"

    # Use a session to automatically manage cookies (including path-based cookies like _xsrf)
    session = requests.Session()

    print("--- Step 1: JWT Login ---")
    login_resp = session.get(login_url, headers={"Authorization": f"bearer {token}"})

    if login_resp.status_code != 200:
        print(f"Login failed: {login_resp.text}")
        return

    # Extract the XSRF token from cookies (session handles path=/hub/ automatically)
    xsrf_token = session.cookies.get("_xsrf")

    if not xsrf_token:
        print("Error: No _xsrf cookie returned by the server.")
        return

    print("Login successful.")

    print("--- Step 2: Priming session ---")

    # Hit home page to ensure XSRF cookie is properly set for /hub/ path
    session.get(f"{base_url}/hub/home", headers={"Authorization": f"token {token}"})
    xsrf_token = session.cookies.get("_xsrf")

    # Prime the API session
    session.get(f"{base_url}/hub/api/user", headers={"Authorization": f"token {token}"})

    print("--- Step 3: Starting server ---")

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
    # Label: Ljocha 2026
    start_server()
