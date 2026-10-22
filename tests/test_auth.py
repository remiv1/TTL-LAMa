"""Tests for authentication functionality."""
from __future__ import annotations

import hashlib
from datetime import datetime, timedelta, timezone
from typing import cast

import pytest
from flask import Flask
from flask.testing import FlaskClient
from sqlalchemy import select
from werkzeug.test import TestResponse

from api.common.db_objects.users import User as DatabaseUser
from api.common.db_objects.users import UserSession
from auth.decorators import require_group
from auth.models import User, UserUpdate


def _csrf_token(client: FlaskClient) -> str:
    response = client.get("/auth/csrf")
    assert response.status_code == 200
    return response.get_json()["csrf_token"]


def _login(
    client: FlaskClient,
    username: str,
    password: str,
    csrf_token: str | None = None,
) -> TestResponse:
    headers = {"X-CSRFToken": csrf_token} if csrf_token else {}
    return client.post(
        "/auth/login",
        json={"username": username, "password": password},
        headers=headers,
    )


def test_internal_login_accepts_valid_credentials_and_rejects_invalid(
    app: Flask,
    login_admin: tuple[str, str],
) -> None:
    """Test that internal login accepts valid credentials and rejects invalid ones."""
    client = app.test_client()
    csrf_token = _csrf_token(client)
    username, password = login_admin

    accepted = _login(client, username, password, csrf_token)
    rejected = _login(client, username, "incorrect-password", csrf_token)
    unknown = _login(client, "unknown-user", "incorrect-password", csrf_token)

    assert accepted.status_code == 200
    assert accepted.get_json()["user"]["username"] == username
    assert rejected.status_code == unknown.status_code == 401
    assert rejected.get_json() == unknown.get_json()


def test_disabled_user_cannot_authenticate(
    app: Flask,
    login_admin: tuple[str, str],
) -> None:
    """Test that a disabled user cannot authenticate."""
    manager = app.extensions["auth_manager"]
    admin_id = manager.users.db_session().scalar(
        select(DatabaseUser.id).where(
            DatabaseUser.username
            == cast(str, app.config["TEST_ADMIN_USERNAME"])
        )
    )
    assert admin_id is not None
    manager.users.update_user(UserUpdate(user_id=admin_id, enabled=False))

    client = app.test_client()
    response = _login(client, *login_admin, csrf_token=_csrf_token(client))

    assert response.status_code == 401


def test_session_is_hashed_expires_and_can_be_revoked(
    app: Flask,
    login_admin: tuple[str, str],
) -> None:
    """Test that a session is hashed, expires correctly, and can be revoked."""
    client = app.test_client()
    csrf_token = _csrf_token(client)
    assert _login(client, *login_admin, csrf_token=csrf_token).status_code == 200
    auth_cookie = client.get_cookie("ttl-lama_session")
    assert auth_cookie is not None
    raw_token = auth_cookie.value

    database = app.extensions["database_config"]
    session = database.session()
    stored = session.scalar(
        select(UserSession).where(
            UserSession.session_token == hashlib.sha256(raw_token.encode()).hexdigest()
        )
    )
    assert stored is not None
    stored.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    session.commit()

    assert client.get("/auth/me").status_code == 401
    assert session.scalar(
        select(UserSession).where(UserSession.session_token == stored.session_token)
    ) is None

    csrf_token = _csrf_token(client)
    assert _login(client, *login_admin, csrf_token=csrf_token).status_code == 200
    csrf_token = _csrf_token(client)
    assert client.post(
        "/auth/logout",
        headers={"X-CSRFToken": csrf_token},
    ).status_code == 200
    assert client.get("/auth/me").status_code == 401


def test_login_lockout_follows_repeated_failures(
    app: Flask,
    login_admin: tuple[str, str],
) -> None:
    """Test that repeated failed login attempts trigger a lockout."""
    client = app.test_client()
    csrf_token = _csrf_token(client)
    username, password = login_admin

    for _ in range(6):
        assert _login(client, username, "incorrect-password", csrf_token).status_code == 401

    assert _login(client, username, password, csrf_token).status_code == 401


def test_group_authorization_returns_401_and_403(
    app: Flask,
    login_admin: tuple[str, str],
) -> None:
    """Test that group-based authorization returns 401 for unauthenticated users
    and 403 for unauthorized users."""
    def admin_route() -> tuple[dict[str, str], int]:
        return {"status": "ok"}, 200

    protected = require_group("ADMIN")(admin_route)
    app.add_url_rule("/test/admin", view_func=protected)
    client = app.test_client()
    assert client.get("/test/admin").status_code == 401

    username, password = login_admin
    assert _login(client, username, password, _csrf_token(client)).status_code == 200
    assert client.get("/test/admin").status_code == 200

    manager = app.extensions["auth_manager"]
    viewer_user = manager.users.create_user(
        username=f"viewer-{username}",
        email=f"viewer-{username}@localhost",
        password="viewer-password",
        group_names=["VIEWER"],
    )
    viewer = app.test_client()
    assert _login(
        viewer,
        f"viewer-{username}",
        "viewer-password",
        _csrf_token(viewer),
    ).status_code == 200
    try:
        assert viewer.get("/test/admin").status_code == 403
    finally:
        manager.users.delete_user(int(viewer_user.id))


def test_csrf_is_required_for_login_and_logout(
    app: Flask,
    login_admin: tuple[str, str],
) -> None:
    """Test that CSRF protection is enforced for login and logout endpoints."""
    client = app.test_client()
    assert _login(client, *login_admin).status_code == 400
    csrf_token = _csrf_token(client)
    assert _login(client, *login_admin, csrf_token=csrf_token).status_code == 200
    assert client.post("/auth/logout").status_code == 400
    assert client.get("/auth/me").status_code == 200
    assert client.post(
        "/auth/logout",
        headers={"X-CSRFToken": csrf_token},
    ).status_code == 200


def test_oidc_callback_success_and_invalid_callback(
    app: Flask,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test the OIDC callback for both successful and invalid authentication."""
    manager = app.extensions["auth_manager"]
    manager.mode = "external"
    user = User(
        id="oidc-subject",
        username="oidc-user",
        groups=["VIEWER"],
        auth_source="external",
    )
    monkeypatch.setattr(manager, "complete_login", lambda: (user, "opaque-session"))
    client = app.test_client()

    accepted = client.get("/auth/callback")
    assert accepted.status_code == 200
    assert accepted.get_json()["user"]["username"] == "oidc-user"
    auth_cookie = client.get_cookie("ttl-lama_session")
    assert auth_cookie is not None
    assert auth_cookie.value == "opaque-session"

    def invalid_callback() -> None:
        raise ValueError("invalid state")

    monkeypatch.setattr(manager, "complete_login", invalid_callback)
    rejected = app.test_client().get("/auth/callback")
    assert rejected.status_code == 401
    assert rejected.get_json()["error"] == "OIDC authentication failed"
