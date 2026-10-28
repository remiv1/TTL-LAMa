"""Tests for authentication routes."""

from typing import cast

import pytest
from flask import Response
from flask import Flask
from flask.testing import FlaskClient
from werkzeug.test import TestResponse

from auth.backends import OIDCAuthBackend
from auth.manager import AuthManager


def _csrf_headers(client: FlaskClient) -> dict[str, str]:
    response = client.get("/api/v1/csrf")
    assert response.status_code == 200

    payload = cast(dict[str, object], response.get_json())
    assert isinstance(payload, dict)
    token = payload.get("csrf_token")
    assert isinstance(token, str)
    return {"X-CSRFToken": token}


def _assert_auth_cookie_not_set(response: TestResponse, app: Flask) -> None:
    cookie_name = cast(str, app.config["AUTH_COOKIE_NAME"])
    assert not any(
        value.startswith(f"{cookie_name}=")
        for value in response.headers.getlist("Set-Cookie")
    )


def test_login_starts_oidc_flow(
        oidc_app: Flask,
        monkeypatch: pytest.MonkeyPatch
) -> None:
    """Test that the login route initiates the OIDC flow."""
    def authorize_redirect(redirect_uri: str) -> Response:
        """Mock authorize_redirect to capture the redirect URI."""
        redirect_uris.append(redirect_uri)
        return Response(
            status=302,
            headers={"Location": "https://dex.example/authorize"}
        )
    manager = cast(AuthManager, oidc_app.extensions["auth_manager"])
    backend = cast(OIDCAuthBackend, manager.backend)
    redirect_uris: list[str] = []

    monkeypatch.setattr(
        backend.oidc_client,
        "authorize_redirect",
        authorize_redirect,
    )

    response = oidc_app.test_client().get("/auth/login")

    assert response.status_code == 302
    assert response.headers["Location"] == "https://dex.example/authorize"
    assert redirect_uris == [oidc_app.config["OIDC_REDIRECT_URI"]]

def test_internal_login_sets_http_only_cookie(app: Flask) -> None:
    """Sets the session cookie without exposing the token in the response body."""
    client = app.test_client()
    username = cast(str, app.config["TEST_ADMIN_USERNAME"])

    response = client.post(
        "/auth/login",
        json={
            "username": username,
            "password": "correct-horse-battery",
        },
        headers=_csrf_headers(client),
    )

    assert response.status_code == 200
    assert response.headers["Cache-Control"] == "no-store"

    payload = response.get_json()
    assert isinstance(payload, dict)
    assert payload["user"]["username"] == username
    assert "access_token" not in payload

    cookie_name = cast(str, app.config["AUTH_COOKIE_NAME"])
    cookie_header = next(
        value
        for value in response.headers.getlist("Set-Cookie")
        if value.startswith(f"{cookie_name}=")
    )
    assert "HttpOnly" in cookie_header
    assert "SameSite=Lax" in cookie_header


def test_internal_login_rejects_invalid_credentials_without_cookie(app: Flask) -> None:
    """Rejects invalid credentials without setting the authentication cookie."""
    client = app.test_client()
    username = cast(str, app.config["TEST_ADMIN_USERNAME"])

    response = client.post(
        "/auth/login",
        json={"username": username, "password": "wrong-password"},
        headers=_csrf_headers(client),
    )

    assert response.status_code == 401
    assert response.get_json() == {"error": "Invalid username or password"}
    _assert_auth_cookie_not_set(response, app)


def test_internal_login_rejects_non_object_json_without_cookie(app: Flask) -> None:
    """Rejects a non-object JSON payload without setting the authentication cookie."""
    client = app.test_client()

    response = client.post(
        "/auth/login",
        json=["not", "an", "object"],
        headers=_csrf_headers(client),
    )

    assert response.status_code == 400
    _assert_auth_cookie_not_set(response, app)


def test_internal_login_is_unavailable_in_external_mode(oidc_app: Flask) -> None:
    """Rejects credential login when external authentication is configured."""
    client = oidc_app.test_client()

    response = client.post(
        "/auth/login",
        json={"username": "alice", "password": "secret"},
        headers=_csrf_headers(client),
    )

    assert response.status_code == 405
    _assert_auth_cookie_not_set(response, oidc_app)


def test_internal_login_requires_csrf_token(app: Flask) -> None:
    """Rejects a cookie-based login without a CSRF token."""
    client = app.test_client()

    response = client.post(
        "/auth/login",
        json={
            "username": cast(str, app.config["TEST_ADMIN_USERNAME"]),
            "password": "correct-horse-battery",
        },
    )

    assert response.status_code == 400
    _assert_auth_cookie_not_set(response, app)
