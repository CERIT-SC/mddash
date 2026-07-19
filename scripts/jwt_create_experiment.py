#!/usr/bin/env python3
"""
Create a test experiment end-to-end via the MDDash API.

A standalone manual test script that:
1. Logs in via EGI JWT authentication,
2. Waits for the singleuser server to be ready,
3. Completes the OAuth flow for mddash session,
4. Creates a molecular dynamics experiment (PDB: 1L2Y) via the dashboard API.
5. Generates a passwordless login URL by requesting a token from the auth service.

Requires a `TOKEN` environment variable containing a valid EGI JWT access token.

Usage:
    TOKEN=<jwt-token> python scripts/jwt_create_experiment.py

Output:
    - Experiment creation result
    - Passwordless login URL that can be shared for direct access
"""

import json
import os
import time

import requests


def log_request(method, url, headers=None, data=None):
    """Log outgoing request details."""
    print(f"\n[REQUEST] {method} {url}")
    if headers:
        safe_headers = {k: ("***" if k.lower() in ("authorization", "cookie") else v) for k, v in headers.items()}
        print(f"  Headers: {safe_headers}")
    if data:
        print(f"  Data: {data}")


def log_response(resp, prefix=""):
    """Log response details."""
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
    NOTEBOOKS_REPO = "https://github.com/sb-ncbr/mddash-notebooks.git"

    # Passwordless access configuration
    GENERATE_PASSWORDLESS_URL = True  # Set to False to skip passwordless URL generation

    session = requests.Session()

    # Step 1: JWT Login
    print("--- Step 1: JWT Login ---")
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

    # Step 2: Prime the session
    print("--- Step 2: Priming session ---")

    log_request("GET", f"{base_url}/hub/home", {"Authorization": "token ***"})
    resp1 = session.get(f"{base_url}/hub/home", headers={"Authorization": f"token {token}"})
    log_response(resp1, "HOME")

    log_request("GET", user_api_url, {"Authorization": "token ***"})
    resp2 = session.get(user_api_url, headers={"Authorization": f"token {token}"})
    log_response(resp2, "USER_API")

    xsrf_token = session.cookies.get("_xsrf")
    print(f"XSRF token: {xsrf_token[:20]}..." if xsrf_token else "No XSRF token")

    # Step 3: Check server status from /hub/api/user
    print("--- Step 3: Checking server status ---")
    user_info = resp2.json()
    servers = user_info.get("servers", {})

    default_server = servers.get("", {})
    server_url_path = default_server.get("url", "")

    print("Server info from API:")
    print(f"  ready: {default_server.get('ready', 'N/A')}")
    print(f"  stopped: {default_server.get('stopped', 'N/A')}")
    print(f"  url: {server_url_path}")

    # Step 4: Wait for server to be ready
    print("--- Step 4: Waiting for singleuser server to come up ---")
    max_retries = 60
    retry_interval = 5
    server_ready = False

    for i in range(max_retries):
        print(f"\n--- Poll attempt {i + 1}/{max_retries} ---")

        log_request("GET", user_api_url, {"Authorization": "token ***"})
        resp = session.get(user_api_url, headers={"Authorization": f"token {token}"})
        log_response(resp, "POLL")

        if resp.status_code == 200:
            user_info = resp.json()
            servers = user_info.get("servers", {})
            default_server = servers.get("", {})

            is_ready = default_server.get("ready", False)
            is_stopped = default_server.get("stopped", True)

            print(f"Server status - ready: {is_ready}, stopped: {is_stopped}")

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

    # Step 5: Establish mddash-auth session via OAuth flow
    print("--- Step 5: Establishing mddash-auth session ---")
    dash_url = f"{base_url}{server_url_path}dash/"
    print(f"Accessing {dash_url} to complete OAuth flow...")

    log_request("GET", dash_url)
    resp = session.get(dash_url, allow_redirects=True)
    log_response(resp, "DASH_OAUTH")

    if "mddash-auth" not in session.cookies:
        print("Error: mddash-auth cookie not set after OAuth flow.")
        return

    print(f"mddash-auth cookie obtained: {session.cookies['mddash-auth'][:30]}...")

    # Step 6: Create experiment via POST /dash/api/experiments
    print("--- Step 6: Creating experiment ---")

    create_url = f"{base_url}{server_url_path}dash/api/experiments"
    experiment_data = {
        "experiment-name": EXPERIMENT_NAME,
        "type": "pdb",
        "pdb-id": PDB_ID,
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

    # Step 7: Request passwordless login URL from auth service
    if GENERATE_PASSWORDLESS_URL:
        print("--- Step 7: Requesting passwordless login URL ---")

        # Call the /create-login-token endpoint which:
        # 1. Validates the existing mddash-auth cookie
        # 2. Creates a new session token server-side
        # 3. Returns the token so we can construct the login URL
        create_token_url = f"{base_url}{server_url_path}dash/auth/create-login-token"

        log_request("POST", create_token_url)
        resp = session.post(create_token_url)
        log_response(resp, "CREATE_LOGIN_TOKEN")

        if resp.status_code == 200:
            result = resp.json()
            login_url = result.get("login_url")
            expires_in = result.get("expires_in", 3600)

            print("\n" + "=" * 60)
            print("PASSWORDLESS LOGIN URL:")
            print("=" * 60)
            print(login_url)
            print("=" * 60)
            print(f"\nThis token is valid for {expires_in // 60} minutes.")
            print("The token is one-time use: consuming it will invalidate it.")
            print()
        else:
            print(f"\nFailed to generate passwordless URL. Status: {resp.status_code}")
            error_detail = resp.json().get("error", resp.text) if resp.content else "Unknown error"
            print(f"Error: {error_detail}")
            print()


if __name__ == "__main__":
    create_experiment()
