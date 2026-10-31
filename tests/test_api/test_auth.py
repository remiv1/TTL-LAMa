"""Tests for the authentication API."""

from typing import cast

from flask import Flask
from flask.testing import FlaskClient

from api.common.repositories import UserRepository
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
    persisted_user = manager.user_service.get_by_username(username)
    assert persisted_user is not None
    assert persisted_user.last_login is not None

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
    manager = cast(AuthManager, app.extensions["auth_manager"])
    user = manager.user_service.get_by_username(username)
    assert user is not None
    assert user.last_login is None


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


def test_self_service_password_change_revokes_all_sessions(app: Flask) -> None:
    """An ordinary user can change their password and revoke every active session."""
    client = app.test_client()
    admin_username = cast(str, app.config["TEST_ADMIN_USERNAME"])
    admin_login = client.post(
        "/api/v1/auth",
        headers={"Authorization": "Bearer unused"},
        json={"username": admin_username, "password": "correct-horse-battery"},
    )
    admin_payload = cast(dict[str, object], admin_login.get_json())
    admin_token = cast(str, admin_payload["access_token"])
    old_password = "old-user-password"
    new_password = "new-user-password"
    username = f"self-service-{admin_username}"

    created = client.post(
        "/api/v1/admin/users",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"username": username, "password": old_password},
    )
    assert created.status_code == 201

    user_tokens: list[str] = []
    for _ in range(2):
        login = client.post(
            "/api/v1/auth",
            headers={"Authorization": "Bearer unused"},
            json={"username": username, "password": old_password},
        )
        assert login.status_code == 200
        payload = cast(dict[str, object], login.get_json())
        user_tokens.append(cast(str, payload["access_token"]))

    manager = cast(AuthManager, app.extensions["auth_manager"])
    wrong_password = client.patch(
        "/api/v1/users/me/password",
        headers={"Authorization": f"Bearer {user_tokens[0]}"},
        json={"current_password": "incorrect", "new_password": new_password},
    )
    assert wrong_password.status_code == 401
    assert manager.get_current_user(user_tokens[0]) is not None

    changed = client.patch(
        "/api/v1/users/me/password",
        headers={"Authorization": f"Bearer {user_tokens[0]}"},
        json={"current_password": old_password, "new_password": new_password},
    )
    assert changed.status_code == 204
    assert changed.get_data() == b""
    assert changed.headers["Cache-Control"] == "no-store"
    assert all(manager.get_current_user(token) is None for token in user_tokens)

    old_login = client.post(
        "/api/v1/auth",
        headers={"Authorization": "Bearer unused"},
        json={"username": username, "password": old_password},
    )
    new_login = client.post(
        "/api/v1/auth",
        headers={"Authorization": "Bearer unused"},
        json={"username": username, "password": new_password},
    )
    assert old_login.status_code == 401
    assert new_login.status_code == 200


def test_self_service_password_change_rejects_account_without_internal_credential(
    app: Flask,
) -> None:
    """An authenticated account without an internal credential cannot change passwords."""
    database = app.extensions["database_config"]
    user = UserRepository(database.session()).create(
        username=f"passwordless-{app.config['TEST_ADMIN_USERNAME']}"
    )
    database.session().commit()
    manager = cast(AuthManager, app.extensions["auth_manager"])
    token = manager.session_service.create(str(user.id))

    response = app.test_client().patch(
        "/api/v1/users/me/password",
        headers={"Authorization": f"Bearer {token}"},
        json={"current_password": "unused", "new_password": "new-password"},
    )

    assert response.status_code == 409
    assert response.get_json() == {
        "error": "This account has no unique internal password credential"
    }


def test_api_auth_requires_csrf_token(app: Flask) -> None:
    """Rejects cookie-based login without a CSRF token."""
    client = app.test_client()

    response = client.post(
        "/api/v1/auth",
        json={"username": "admin", "password": "secret"},
    )

    assert response.status_code == 400
