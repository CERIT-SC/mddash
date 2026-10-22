"""Unit tests for MDRepo OAuth routes."""

import json
from base64 import b64decode, b64encode
from collections.abc import Iterator
from dataclasses import replace
from http import HTTPStatus
from typing import Any
from unittest.mock import patch
from urllib.parse import quote

import httpx
import itsdangerous
import pytest
import respx
from app import create_app
from clients import Clients
from clients.mdrepo import MDRepoClient
from fastapi import FastAPI
from httpx import AsyncClient
from modules.mdrepo.tokens import MDREPO_REFRESH_TOKEN_KEY, MDREPO_TOKEN_EXPIRES_AT, MDREPO_TOKEN_KEY
from sqlalchemy.ext.asyncio import AsyncSession

SECRET = "test_secret_key"
MDREPO = "https://mdrepo.test"
TOKEN_URL = f"{MDREPO}/oauth/token"


@pytest.fixture
def app(db_session: AsyncSession, clients: Clients) -> FastAPI:
    mdrepo = MDRepoClient(clients.http, url=MDREPO, token_url=TOKEN_URL)
    return create_app(clients=replace(clients, mdrepo=mdrepo), session_secret=SECRET)


@pytest.fixture(autouse=True)
def _mdrepo_url() -> Iterator[None]:
    with patch("modules.mdrepo.router.MDREPO_URL", MDREPO):
        yield


def set_session(client: AsyncClient, data: dict[str, Any]) -> None:
    """Store `data` in the signed session cookie the way Starlette's SessionMiddleware does."""
    signed = itsdangerous.TimestampSigner(SECRET).sign(b64encode(json.dumps(data).encode()))
    client.cookies.set("session", signed.decode(), domain="testserver.local")


def get_session(client: AsyncClient) -> dict[str, Any]:
    cookie = client.cookies.get("session")
    if not cookie:
        return {}
    return json.loads(b64decode(itsdangerous.TimestampSigner(SECRET).unsign(cookie)))


class TestMDRepoRoutes:
    """Test MDRepo OAuth routes."""

    async def test_get_status_no_token(self, client: AsyncClient) -> None:
        response = await client.get("/dash/api/mdrepo/status")
        assert response.status_code == HTTPStatus.OK
        assert response.json() == {"authenticated": False}

    async def test_get_status_valid_token(self, client: AsyncClient, http_mock: respx.MockRouter) -> None:
        me = http_mock.get(f"{MDREPO}/api/me").mock(return_value=httpx.Response(200, json={}))
        set_session(client, {MDREPO_TOKEN_KEY: "test_access_token", MDREPO_TOKEN_EXPIRES_AT: 9999999999.0})

        response = await client.get("/dash/api/mdrepo/status")

        assert response.status_code == HTTPStatus.OK
        assert response.json() == {"authenticated": True, "mdrepo_url": MDREPO}
        assert me.calls.last.request.headers["Authorization"] == "Bearer test_access_token"

    async def test_get_status_expired_token(self, client: AsyncClient, http_mock: respx.MockRouter) -> None:
        http_mock.get(f"{MDREPO}/api/me").mock(return_value=httpx.Response(401))
        set_session(client, {MDREPO_TOKEN_KEY: "test_access_token", MDREPO_TOKEN_EXPIRES_AT: 0.0})

        response = await client.get("/dash/api/mdrepo/status")

        assert response.status_code == HTTPStatus.OK
        assert response.json()["authenticated"] is False
        # Token should be cleared from session
        assert MDREPO_TOKEN_KEY not in get_session(client)

    @patch("modules.mdrepo.router.MDREPO_CLIENT_ID", "")
    @patch("modules.mdrepo.router.MDREPO_CLIENT_SECRET", "")
    @patch("modules.mdrepo.router.MDREPO_REDIRECT_URI", "")
    async def test_initiate_auth_no_config(self, client: AsyncClient) -> None:
        response = await client.get("/dash/api/mdrepo/auth")
        assert response.status_code == HTTPStatus.SERVICE_UNAVAILABLE
        assert response.json()["type"] == "urn:mddash:mdrepo-not-configured"

    @patch("modules.mdrepo.router.MDREPO_CLIENT_ID", "test_client_id")
    @patch("modules.mdrepo.router.MDREPO_CLIENT_SECRET", "test_client_secret")
    @patch("modules.mdrepo.router.MDREPO_REDIRECT_URI", "http://localhost/callback")
    @patch("modules.mdrepo.router.MDREPO_AUTHORIZE_URL", "http://mdrepo.example.com/oauth/authorize")
    @patch("modules.mdrepo.router.MDREPO_SCOPES", "read write")
    async def test_initiate_auth_with_config(self, client: AsyncClient) -> None:
        response = await client.get("/dash/api/mdrepo/auth?return_url=/test")
        assert response.status_code == HTTPStatus.FOUND
        assert response.headers["location"].startswith("http://mdrepo.example.com/oauth/authorize?")

        session = get_session(client)
        assert "mdrepo_oauth_state" in session
        assert session["mdrepo_return_url"] == "/test"

    @pytest.mark.parametrize(
        ("return_url", "expected"),
        [
            pytest.param(
                "/dash/experiments/exp1?simulation=md.simulation.json&step=4",
                "/dash/experiments/exp1?simulation=md.simulation.json&step=4",
                id="path-with-query",
            ),
            pytest.param("https://evil.com/phish", "/", id="absolute-https"),
            pytest.param("http://evil.com", "/", id="absolute-http"),
            pytest.param("//evil.com/phish", "/", id="protocol-relative"),
            pytest.param("/\\evil.com", "/", id="backslash"),
            pytest.param("\\\\evil.com", "/", id="leading-backslashes"),
            pytest.param("evil.com", "/", id="bare-host"),
            pytest.param("", "/", id="empty"),
        ],
    )
    @patch("modules.mdrepo.router.MDREPO_CLIENT_ID", "test_client_id")
    @patch("modules.mdrepo.router.MDREPO_CLIENT_SECRET", "test_client_secret")
    @patch("modules.mdrepo.router.MDREPO_REDIRECT_URI", "http://localhost/callback")
    @patch("modules.mdrepo.router.MDREPO_AUTHORIZE_URL", "http://mdrepo.example.com/oauth/authorize")
    async def test_initiate_auth_return_url_open_redirect_guard(
        self, client: AsyncClient, return_url: str, expected: str
    ) -> None:
        """The stored return URL must be a same-origin path; anything else 302s to / (CWE-601)."""
        response = await client.get(f"/dash/api/mdrepo/auth?return_url={quote(return_url, safe='')}")
        assert response.status_code == HTTPStatus.FOUND
        assert get_session(client)["mdrepo_return_url"] == expected

    async def test_oauth_callback_success(self, client: AsyncClient, http_mock: respx.MockRouter) -> None:
        http_mock.post(TOKEN_URL).mock(
            return_value=httpx.Response(
                200,
                json={"access_token": "new_access_token", "refresh_token": "new_refresh_token", "expires_in": 3600},
            )
        )
        set_session(client, {"mdrepo_oauth_state": "test_state", "mdrepo_return_url": "/dashboard"})

        response = await client.get("/dash/api/mdrepo/callback?code=test_code&state=test_state")

        assert response.status_code == HTTPStatus.FOUND
        assert response.headers["location"] == "/dashboard?mdrepo_auth=success"
        session = get_session(client)
        assert session[MDREPO_TOKEN_KEY] == "new_access_token"
        assert session[MDREPO_REFRESH_TOKEN_KEY] == "new_refresh_token"
        assert MDREPO_TOKEN_EXPIRES_AT in session
        # State should be cleared
        assert "mdrepo_oauth_state" not in session

    async def test_oauth_callback_no_refresh_token(self, client: AsyncClient, http_mock: respx.MockRouter) -> None:
        http_mock.post(TOKEN_URL).mock(
            return_value=httpx.Response(200, json={"access_token": "new_access_token", "expires_in": 3600})
        )
        set_session(client, {"mdrepo_oauth_state": "test_state", "mdrepo_return_url": "/dashboard"})

        response = await client.get("/dash/api/mdrepo/callback?code=test_code&state=test_state")

        assert response.status_code == HTTPStatus.FOUND
        session = get_session(client)
        assert session[MDREPO_TOKEN_KEY] == "new_access_token"
        assert MDREPO_REFRESH_TOKEN_KEY not in session
        assert MDREPO_TOKEN_EXPIRES_AT in session

    async def test_oauth_callback_error(self, client: AsyncClient) -> None:
        set_session(client, {"mdrepo_oauth_state": "test_state", "mdrepo_return_url": "/dashboard"})

        response = await client.get("/dash/api/mdrepo/callback?error=access_denied&state=test_state")

        assert response.status_code == HTTPStatus.FOUND
        assert "mdrepo_error=" in response.headers["location"]
        assert "/dashboard" in response.headers["location"]

    async def test_oauth_callback_invalid_state(self, client: AsyncClient) -> None:
        set_session(client, {"mdrepo_oauth_state": "correct_state", "mdrepo_return_url": "/dashboard"})

        response = await client.get("/dash/api/mdrepo/callback?code=test_code&state=wrong_state")

        assert response.status_code == HTTPStatus.FOUND
        assert "mdrepo_error=Invalid+state+parameter" in response.headers["location"]

    async def test_oauth_callback_error_preserves_return_url_query(self, client: AsyncClient) -> None:
        """Error params merge into a return URL that already carries its own query string."""
        set_session(
            client,
            {
                "mdrepo_oauth_state": "correct_state",
                "mdrepo_return_url": "/dash/experiments/exp1?simulation=md.simulation.json&step=4",
            },
        )

        response = await client.get("/dash/api/mdrepo/callback?code=test_code&state=wrong_state")

        assert response.status_code == HTTPStatus.FOUND
        assert response.headers["location"] == (
            "/dash/experiments/exp1?simulation=md.simulation.json&step=4&mdrepo_error=Invalid+state+parameter"
        )

    async def test_oauth_callback_error_on_plain_return_url(self, client: AsyncClient) -> None:
        """Error params append to a return URL that has no query string of its own."""
        set_session(client, {"mdrepo_oauth_state": "correct_state", "mdrepo_return_url": "/dash/experiments/exp1"})

        response = await client.get("/dash/api/mdrepo/callback?code=test_code&state=wrong_state")

        assert response.status_code == HTTPStatus.FOUND
        assert response.headers["location"] == "/dash/experiments/exp1?mdrepo_error=Invalid+state+parameter"

    async def test_oauth_callback_token_exchange_failed(self, client: AsyncClient, http_mock: respx.MockRouter) -> None:
        http_mock.post(TOKEN_URL).mock(return_value=httpx.Response(400, text="Invalid grant"))
        set_session(client, {"mdrepo_oauth_state": "test_state", "mdrepo_return_url": "/dashboard"})

        response = await client.get("/dash/api/mdrepo/callback?code=test_code&state=test_state")

        assert response.status_code == HTTPStatus.FOUND
        assert "mdrepo_error=Token+exchange+failed" in response.headers["location"]

    async def test_oauth_callback_unreachable_token_endpoint(self, client: AsyncClient) -> None:
        """Network failures redirect with an error instead of a 500."""
        set_session(client, {"mdrepo_oauth_state": "test_state", "mdrepo_return_url": "/dashboard"})

        response = await client.get("/dash/api/mdrepo/callback?code=test_code&state=test_state")

        assert response.status_code == HTTPStatus.FOUND
        assert "mdrepo_error=Request+failed" in response.headers["location"]

    async def test_logout(self, client: AsyncClient) -> None:
        set_session(
            client,
            {
                MDREPO_TOKEN_KEY: "test_token",
                MDREPO_REFRESH_TOKEN_KEY: "test_refresh_token",
                MDREPO_TOKEN_EXPIRES_AT: 9999999999.0,
            },
        )

        response = await client.post("/dash/api/mdrepo/logout")

        assert response.status_code == HTTPStatus.OK
        assert response.json()["message"] == "Logged out from MDRepo"
        session = get_session(client)
        assert MDREPO_TOKEN_KEY not in session
        assert MDREPO_REFRESH_TOKEN_KEY not in session
        assert MDREPO_TOKEN_EXPIRES_AT not in session
