#!/usr/bin/env python3
"""Create a test experiment through the MDDash API with EGI JWT authentication."""

import json
import os
import time

import requests


def log_request(method, url, headers=None, data=None):
    print(f"\n[REQUEST] {method} {url}")
    if headers:
        safe_headers = {k: ("***" if k.lower() in ("authorization", "cookie") else v) for k, v in headers.items()}
        print(f"  Headers: {safe_headers}")
    if data:
        print(f"  Data: {data}")


def log_response(resp, prefix=""):
    print(f"\n[RESPONSE {prefix}] Status: {resp.status_code}")
    print(f"  Headers: {dict(resp.headers)}")
    try:
        data = resp.json()
        print(f"  Body (JSON): {json.dumps(data, indent=2)}")
    except:
        print(f"  Body: {resp.text}")
    print()


def create_experiment():
    token = os.getenv("TOKEN")
    if not token:
        print("Error: TOKEN environment variable missing.")
        return

    base_url = "https://mddash-edc.dyn.cloud.e-infra.cz"
    login_url = f"{base_url}/hub/jwt_login"
    user_api_url = f"{base_url}/hub/api/user"

    # Experiment configuration
    EXPERIMENT_NAME = "test-experiment-1L2Y"
    PDB_ID = "1L2Y"
    NOTEBOOKS_REPO = "https://github.com/CERIT-SC/mddash-notebooks.git"

    # Passwordless access configuration
    GENERATE_PASSWORDLESS_URL = True  # Set to False to skip passwordless URL generation

    session = requests.Session()

    print("JWT login.")
    log_request("GET", login_url, {"Authorization": "bearer ***"})
    login_resp = session.get(login_url, headers={"Authorization": f"bearer {token}"})
    log_response(login_resp, "LOGIN")

    if login_resp.status_code != 200:
        print("Login failed!")
        return

    xsrf_token = session.cookies.get("_xsrf")
    if not xsrf_token:
        print("Error: No _xsrf cookie returned by the server.")
        return

    print("Login successful.")
    print(f"Cookies set: {list(session.cookies.keys())}")

    print("Priming session.")

    log_request("GET", f"{base_url}/hub/home", {"Authorization": "token ***"})
    resp1 = session.get(f"{base_url}/hub/home", headers={"Authorization": f"token {token}"})
    log_response(resp1, "HOME")

    log_request("GET", user_api_url, {"Authorization": "token ***"})
    resp2 = session.get(user_api_url, headers={"Authorization": f"token {token}"})
    log_response(resp2, "USER_API")

    xsrf_token = session.cookies.get("_xsrf")
    print(f"XSRF token: {xsrf_token[:20]}..." if xsrf_token else "No XSRF token")

    # Check server status from /hub/api/user
    print("Checking server status.")
    user_info = resp2.json()
    servers = user_info.get("servers", {})

    default_server = servers.get("", {})
    server_url_path = default_server.get("url", "")

    print("Server info from API:")
    print(f"  ready: {default_server.get('ready', 'N/A')}")
    print(f"  stopped: {default_server.get('stopped', 'N/A')}")
    print(f"  url: {server_url_path}")

    # Wait for server to be ready
    print("Waiting for singleuser server to come up.")
    max_retries = 60
    retry_interval = 5
    server_ready = False

    for i in range(max_retries):
        print(f"\nPoll attempt {i + 1}/{max_retries}.")

        log_request("GET", user_api_url, {"Authorization": "token ***"})
        resp = session.get(user_api_url, headers={"Authorization": f"token {token}"})
        log_response(resp, "POLL")

        if resp.status_code == 200:
            user_info = resp.json()
            servers = user_info.get("servers", {})
            default_server = servers.get("", {})

            is_ready = default_server.get("ready", False)
            is_stopped = default_server.get("stopped", True)

            print(f"Server status. Ready: {is_ready}, stopped: {is_stopped}")

            if is_ready and not is_stopped:
                server_ready = True
                server_url_path = default_server.get("url", "")
                break

        time.sleep(retry_interval)

    if not server_ready:
        print("Error: Server did not become ready within timeout.")
        return

    print("Server is ready!")
    print(f"Server URL path: {server_url_path}")

    # Establish mddash-auth session through OAuth flow
    print("Establishing mddash-auth session.")
    dash_url = f"{base_url}{server_url_path}dash/"
    print(f"Accessing {dash_url} to complete OAuth flow...")

    log_request("GET", dash_url)
    resp = session.get(dash_url, allow_redirects=True)
    log_response(resp, "DASH_OAUTH")

    if "mddash-auth" not in session.cookies:
        print("Error: mddash-auth cookie not set after OAuth flow.")
        return

    print(f"mddash-auth cookie obtained: {session.cookies['mddash-auth'][:30]}...")

    # Create experiment with POST /dash/api/experiments
    print("Creating experiment.")

    create_url = f"{base_url}{server_url_path}dash/api/experiments"
    experiment_data = {
        "experiment-name": EXPERIMENT_NAME,
        "type": "pdb",
        "pdb": PDB_ID,
        "notebooks-repo": NOTEBOOKS_REPO,
    }

    print(f"Target URL: {create_url}")
    print(f"Experiment data: {experiment_data}")

    log_request("POST", create_url, data=experiment_data)
    resp = session.post(create_url, data=experiment_data)
    log_response(resp, "CREATE_EXP")

    if resp.status_code in (200, 201):
        result = resp.json()
        print("\nSuccess! Experiment created.")
        if result.get("data"):
            exp_id = result["data"].get("id", "unknown")
            print(f"Experiment ID: {exp_id}")
    else:
        print(f"\nFailed to create experiment. Status: {resp.status_code}")

    # Request passwordless login URL from auth service
    if GENERATE_PASSWORDLESS_URL:
        print("Requesting passwordless login URL.")

        # The endpoint validates the mddash-auth cookie and returns a one-time token for the login URL.
        create_token_url = f"{base_url}{server_url_path}dash/auth/create-login-token"

        log_request("POST", create_token_url)
        resp = session.post(create_token_url)
        log_response(resp, "CREATE_LOGIN_TOKEN")

        if resp.status_code == 200:
            result = resp.json()
            login_url = result.get("login_url")
            expires_in = result.get("expires_in", 3600)

            print("\nPasswordless login URL.")
            print(login_url)
            print(f"\nThis token is valid for {expires_in // 60} minutes.")
            print("The token is one-time use. Consuming it invalidates it.")
            print()
        else:
            print(f"\nFailed to generate passwordless URL. Status: {resp.status_code}")
            error_detail = resp.json().get("error", resp.text) if resp.content else "Unknown error"
            print(f"Error: {error_detail}")
            print()


if __name__ == "__main__":
    create_experiment()
