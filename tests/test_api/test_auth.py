"""Tests for the authentication API."""

from typing import cast

from flask import Flask
from flask.testing import FlaskClient

from auth.manager import AuthManager


def _csrf_headers(client: FlaskClient) -> dict[str, str]:
    response = client.get("/api/v1/csrf")
    assert response.status_code == 200

    payload = cast(dict[str, object], response.get_json())
    assert isinstance(payload, dict)
    token = payload.get("csrf_token")
    assert isinstance(token, str)

    return {"X-CSRFToken": token}


def test_api_auth_returns_bearer_token(app: Flask) -> None:
    """Returns a valid Bearer token after successful internal authentication."""
    client = app.test_client()
    username = cast(str, app.config["TEST_ADMIN_USERNAME"])

    response = client.post(
        "/api/v1/auth",
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
    assert payload["token_type"] == "Bearer"
    assert isinstance(payload["access_token"], str)

    manager = cast(AuthManager, app.extensions["auth_manager"])
    user = manager.get_current_user(payload["access_token"])
    assert user is not None
    assert user.username == username

def test_api_auth_rejects_invalid_credentials(app: Flask) -> None:
    """Rejects invalid credentials without revealing which value was wrong."""
    client = app.test_client()
    username = cast(str, app.config["TEST_ADMIN_USERNAME"])

    response = client.post(
        "/api/v1/auth",
        json={"username": username, "password": "wrong-password"},
        headers=_csrf_headers(client),
    )

    assert response.status_code == 401
    assert response.get_json() == {"error": "Invalid username or password"}


def test_api_auth_rejects_non_object_json(app: Flask) -> None:
    """Rejects a JSON payload that is not an object."""
    client = app.test_client()

    response = client.post(
        "/api/v1/auth",
        json=["not", "an", "object"],
        headers=_csrf_headers(client),
    )

    assert response.status_code == 400


def test_api_auth_is_unavailable_in_external_mode(oidc_app: Flask) -> None:
    """Rejects credential authentication when external auth is configured."""
    client = oidc_app.test_client()

    response = client.post(
        "/api/v1/auth",
        json={"username": "alice", "password": "secret"},
        headers=_csrf_headers(client),
    )

    assert response.status_code == 405


def test_api_auth_requires_csrf_token(app: Flask) -> None:
    """Rejects cookie-based login without a CSRF token."""
    client = app.test_client()

    response = client.post(
        "/api/v1/auth",
        json={"username": "admin", "password": "secret"},
    )

    assert response.status_code == 400
