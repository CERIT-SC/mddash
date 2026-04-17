#!/usr/bin/env python3

import os
import sys
import time
import requests
import json

def log_request(method, url, headers=None, params=None):
    """Log outgoing request details."""
    print(f"\n[REQUEST] {method} {url}")
    if headers:
        safe_headers = {k: ("***" if k.lower() in ("authorization", "cookie") else v) for k, v in headers.items()}
        print(f"  Headers: {safe_headers}")
    if params:
        print(f"  Params: {params}")

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

def wait_for_server():
    token = os.getenv("TOKEN")
    if not token:
        print("Error: TOKEN environment variable missing.")
        return

    base_url = "https://mddash-edc.dyn.cloud.e-infra.cz"
    login_url = f"{base_url}/hub/jwt_login"
    user_api_url = f"{base_url}/hub/api/user"

    session = requests.Session()

    # Step 1: JWT Login
    print("--- Step 1: JWT Login ---")
    log_request("GET", login_url, {"Authorization": "bearer ***"})
    login_resp = session.get(login_url, headers={"Authorization": f"bearer {token}"})
    log_response(login_resp, "LOGIN")

    if login_resp.status_code != 200:
        print(f"Login failed!")
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
    server_state = default_server.get("state", default_server.get("ready", "unknown"))
    server_url_path = default_server.get("url", "")

    print(f"Server info from API:")
    print(f"  ready: {default_server.get('ready', 'N/A')}")
    print(f"  stopped: {default_server.get('stopped', 'N/A')}")
    print(f"  url: {server_url_path}")

    # Step 4: Wait for server to be ready
    print("--- Step 4: Waiting for singleuser server to come up ---")
    max_retries = 60
    retry_interval = 5
    server_ready = False

    for i in range(max_retries):
        print(f"\n--- Poll attempt {i+1}/{max_retries} ---")

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

    # Step 6: Call the dash/api endpoint
    print("--- Step 6: Calling dash/api endpoint ---")

    dash_api_url = f"{base_url}{server_url_path}dash/api/health"

    print(f"Target URL: {dash_api_url}")
    print(f"Current cookies: {list(session.cookies.keys())}")
    for cookie in session.cookies:
        val = session.cookies.get(cookie)
        if val:
            print(f"  {cookie}: {val[:30]}...")

    log_request("GET", dash_api_url)
    resp = session.get(dash_api_url)
    log_response(resp, "DASH_API")

    if resp.status_code == 200:
        print("\nSuccess! Dash API is accessible.")
    else:
        print(f"\nWarning: Got status {resp.status_code}")

if __name__ == "__main__":
    wait_for_server()
