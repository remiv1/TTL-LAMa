"""Tests for authentication routes."""

from datetime import timedelta
from typing import cast

import pytest
from flask import Response
from flask import Flask
from flask.testing import FlaskClient
from werkzeug.test import TestResponse

from api.common.db_objects import User, UserLoginState, UserOIDCUser
from api.common.repositories.leases import utcnow
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


def test_oidc_callback_records_last_login(
    oidc_app: Flask,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The successful OIDC callback persists the user's last login timestamp."""
    database = oidc_app.extensions["database_config"]
    user = User(
        username="oidc-last-login",
        enabled=True,
        is_admin=False,
        oidc_users=[UserOIDCUser(
            subject="oidc-last-login-subject",
            issuer=oidc_app.config["OIDC_ISSUER"],
        )],
    )
    database.session().add(user)
    database.session().commit()

    manager = cast(AuthManager, oidc_app.extensions["auth_manager"])
    backend = cast(OIDCAuthBackend, manager.backend)
    monkeypatch.setattr(
        backend.oidc_client,
        "authorize_access_token",
        lambda: {"userinfo": {"sub": "oidc-last-login-subject"}},
    )

    response = oidc_app.test_client().get("/auth/callback")

    assert response.status_code == 302
    persisted_user = manager.user_service.get_by_username("oidc-last-login")
    assert persisted_user is not None
    assert persisted_user.last_login is not None

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


def test_internal_login_locks_account_after_configured_failures(app: Flask) -> None:
    """Lock an account at the configured threshold across GUI and API login routes."""
    client = app.test_client()
    username = cast(str, app.config["TEST_ADMIN_USERNAME"])
    credentials = {"username": username, "password": "wrong-password"}

    for _ in range(app.config["MAX_CONNECT_RETRY"]):    # type: ignore
        response = client.post(
            "/auth/login",
            json=credentials,
            headers=_csrf_headers(client),
        )
        assert response.status_code == 401
        assert response.get_json() == {"error": "Invalid username or password"}

    user = app.extensions["auth_manager"].user_service.get_by_username(username)
    assert user is not None
    state = app.extensions["database_config"].session().get(UserLoginState, user.id)
    assert state is not None
    assert state.failed_attempts == app.config["MAX_CONNECT_RETRY"]
    assert state.locked
    assert state.locked_until is not None
    assert state.locked_until > utcnow()

    blocked_gui = client.post(
        "/auth/login",
        json={"username": username, "password": "correct-horse-battery"},
        headers=_csrf_headers(client),
    )
    blocked_api = client.post(
        "/api/v1/auth",
        json={"username": username, "password": "correct-horse-battery"},
        headers={"Authorization": "Bearer unused"},
    )

    for blocked in (blocked_gui, blocked_api):
        assert blocked.status_code == 401
        assert blocked.get_json() == {"error": "Invalid username or password"}
    _assert_auth_cookie_not_set(blocked_gui, app)


def test_expired_login_lock_resets_before_counting_next_failure(app: Flask) -> None:
    """An expired lock clears prior failures before evaluating another login."""
    client = app.test_client()
    username = cast(str, app.config["TEST_ADMIN_USERNAME"])
    user = app.extensions["auth_manager"].user_service.get_by_username(username)
    assert user is not None
    session = app.extensions["database_config"].session()
    state = UserLoginState(
        user_id=user.id,
        failed_attempts=app.config["MAX_CONNECT_RETRY"],
        locked=True,
        locked_until=utcnow() - timedelta(seconds=1),
    )
    session.add(state)
    session.commit()

    response = client.post(
        "/auth/login",
        json={"username": username, "password": "wrong-password"},
        headers=_csrf_headers(client),
    )

    assert response.status_code == 401
    updated_state = session.get(UserLoginState, user.id)
    assert updated_state is not None
    assert updated_state.failed_attempts == 1
    assert not updated_state.locked
    assert updated_state.locked_until is None


def test_successful_internal_login_resets_failed_attempts(app: Flask) -> None:
    """A successful login clears failures accumulated before the lock threshold."""
    client = app.test_client()
    username = cast(str, app.config["TEST_ADMIN_USERNAME"])
    for _ in range(app.config["MAX_CONNECT_RETRY"] - 1):    # type: ignore
        response = client.post(
            "/auth/login",
            json={"username": username, "password": "wrong-password"},
            headers=_csrf_headers(client),
        )
        assert response.status_code == 401

    successful = client.post(
        "/auth/login",
        json={"username": username, "password": "correct-horse-battery"},
        headers=_csrf_headers(client),
    )

    assert successful.status_code == 200
    user = app.extensions["auth_manager"].user_service.get_by_username(username)
    assert user is not None
    state = app.extensions["database_config"].session().get(UserLoginState, user.id)
    assert state is not None
    assert state.failed_attempts == 0
    assert not state.locked
    assert state.locked_until is None


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
