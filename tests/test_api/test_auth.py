"""Tests for the authentication API."""

from datetime import timedelta
from typing import cast
from ipaddress import IPv4Network
from urllib.parse import parse_qs, urlsplit

import pytest
from flask import Flask, redirect
from flask.testing import FlaskClient
from sqlalchemy import select

from api.common.db_objects.devices import Device
from api.common.db_objects.leases import Lease
from api.common.db_objects.sessions import Session as UserSession
from api.common.repositories import DeviceRepository, ProfileRepository, UserRepository
from api.common.repositories.leases import utcnow
from api.config.c_profiles import AccessProfile
from auth.manager import AuthManager
from auth.models import UnifiedUser


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


def test_oidc_cli_callback_issues_one_time_ticket_and_exchange_creates_session(
    oidc_app: Flask,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The CLI callback redirects with a ticket, not a session Bearer token."""
    manager = cast(AuthManager, oidc_app.extensions["auth_manager"])
    user = UserRepository(manager.session_service.db_session).create(
        username="oidc-cli-user",
    )
    manager.session_service.db_session.commit()
    monkeypatch.setattr(manager.backend, "begin_login", lambda: redirect("https://idp.example"))
    monkeypatch.setattr(
        manager.backend,
        "complete_login",
        lambda: UnifiedUser.from_db_user(user),
    )
    callback_url = "http://127.0.0.1:43210/callback"
    cli_state = "state-value-that-is-long-enough-123456"
    client = oidc_app.test_client()

    login = client.get(
        "/auth/login",
        query_string={"cli_callback_url": callback_url, "cli_state": cli_state},
    )
    assert login.status_code == 302
    assert login.headers["Location"] == "https://idp.example"

    callback = client.get("/auth/callback?code=provider-code&state=oauth-state")
    assert callback.status_code == 302
    assert callback.headers["Cache-Control"] == "no-store"
    callback_url_parts = urlsplit(callback.headers["Location"])
    callback_parameters = parse_qs(callback_url_parts.query)
    assert callback_url_parts.scheme == "http"
    assert callback_url_parts.netloc == "127.0.0.1:43210"
    assert callback_url_parts.path == "/callback"
    assert callback_parameters["state"] == [cli_state]
    assert "access_token" not in callback_parameters
    assert "session_token" not in callback_parameters

    ticket = callback_parameters["ticket"][0]
    token_response = client.post(
        "/api/v1/auth/oidc/exchange",
        json={"ticket": ticket},
    )
    assert token_response.status_code == 200
    assert token_response.headers["Cache-Control"] == "no-store"
    payload = cast(dict[str, object], token_response.get_json())
    token = cast(str, payload["access_token"])
    assert manager.get_current_user(token) is not None
    assert ticket not in token_response.get_data(as_text=True)

    replay = client.post(
        "/api/v1/auth/oidc/exchange",
        json={"ticket": ticket},
    )
    assert replay.status_code == 401
    assert manager.get_current_user(token) is not None


def test_oidc_cli_login_rejects_non_loopback_callback(oidc_app: Flask) -> None:
    """The OIDC login route refuses callback URLs outside IPv4 loopback."""
    response = oidc_app.test_client().get(
        "/auth/login",
        query_string={
            "cli_callback_url": "http://192.0.2.1:1234/callback",
            "cli_state": "state-value-that-is-long-enough-123456",
        },
    )

    assert response.status_code == 400


def test_oidc_provider_denial_returns_to_the_waiting_cli(
    oidc_app: Flask,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A provider denial returns a state-bound error to the loopback listener."""
    manager = cast(AuthManager, oidc_app.extensions["auth_manager"])
    monkeypatch.setattr(manager.backend, "begin_login", lambda: redirect("https://idp.example"))
    callback_url = "http://127.0.0.1:43210/callback"
    cli_state = "state-value-that-is-long-enough-123456"
    client = oidc_app.test_client()

    login = client.get(
        "/auth/login",
        query_string={"cli_callback_url": callback_url, "cli_state": cli_state},
    )
    assert login.status_code == 302

    denial = client.get("/auth/callback?error=access_denied&state=oauth-state")
    assert denial.status_code == 302
    assert denial.headers["Cache-Control"] == "no-store"
    parameters = parse_qs(urlsplit(denial.headers["Location"]).query)
    assert parameters == {"state": [cli_state], "error": ["access_denied"]}
    assert "ticket" not in parameters


def test_oidc_device_authorization_waits_for_provider_approval(
    oidc_app: Flask,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Device polling creates a Bearer only after the provider confirms approval."""
    manager = cast(AuthManager, oidc_app.extensions["auth_manager"])
    user = UserRepository(manager.session_service.db_session).create(
        username="oidc-device-user",
    )
    manager.session_service.db_session.commit()
    unified_user = UnifiedUser.from_db_user(user)
    def begin_device(
        _client_id: str,
        _client_secret: str,
    ) -> dict[str, object]:
        return {
            "device_code": "private-device-code",
            "user_code": "ABCD-EFGH",
            "verification_uri": "https://idp.example/device",
            "expires_in": 300,
            "interval": 5,
        }

    monkeypatch.setattr(manager.backend, "begin_device_authorization", begin_device)
    poll_results: list[dict[str, object]] = [
        {"status": "pending"},
        {"status": "complete", "user": unified_user},
    ]
    poll_index = 0

    def poll_device(
        _device_code: str,
        _client_id: str,
        _client_secret: str,
    ) -> dict[str, object]:
        nonlocal poll_index
        result = poll_results[poll_index]
        poll_index += 1
        return result

    monkeypatch.setattr(
        manager.backend,
        "poll_device_authorization",
        poll_device,
    )
    client = oidc_app.test_client()

    start = client.post("/api/v1/auth/oidc/device", json={})
    assert start.status_code == 200
    assert start.headers["Cache-Control"] == "no-store"
    assert start.get_json()["device_code"] == "private-device-code"

    pending = client.post(
        "/api/v1/auth/oidc/device/poll",
        json={"device_code": "private-device-code"},
    )
    assert pending.status_code == 200
    assert pending.get_json() == {"status": "pending"}
    assert manager.session_service.db_session.scalar(
        select(UserSession.id).where(UserSession.user_id == str(user.id))
    ) is None

    complete = client.post(
        "/api/v1/auth/oidc/device/poll",
        json={"device_code": "private-device-code"},
    )
    assert complete.status_code == 200
    assert complete.headers["Cache-Control"] == "no-store"
    token_payload = cast(dict[str, object], complete.get_json())
    token = cast(str, token_payload["access_token"])
    assert token_payload["status"] == "complete"
    assert manager.get_current_user(token) is not None


def test_current_user_lists_expirations_without_exposing_session_hash(app: Flask) -> None:
    """The current-user endpoint returns active expirations but no token hashes."""
    manager = cast(AuthManager, app.extensions["auth_manager"])
    username = cast(str, app.config["TEST_ADMIN_USERNAME"])
    user = manager.user_service.get_by_username(username)
    assert user is not None
    first_token = manager.session_service.create(str(user.id))
    second_token = manager.session_service.create(str(user.id))

    response = app.test_client().get(
        "/api/v1/users/me",
        headers={"Authorization": f"Bearer {first_token}"},
    )

    assert response.status_code == 200
    assert response.headers["Cache-Control"] == "no-store"
    payload = cast(dict[str, object], response.get_json())
    assert payload["user"] == {
        "id": str(user.id),
        "username": username,
        "email": user.email,
        "is_admin": user.is_admin,
    }
    sessions = cast(list[dict[str, object]], payload["sessions"])
    assert len(sessions) == 2
    assert all(isinstance(item["expires_at"], str) for item in sessions)
    assert "token_hash" not in response.get_data(as_text=True)
    assert first_token not in response.get_data(as_text=True)
    assert second_token not in response.get_data(as_text=True)


def test_current_user_overview_only_returns_owned_resources(app: Flask) -> None:
    """An ordinary user sees their resources and no other user's data."""
    database = app.extensions["database_config"]
    database_session = database.session()
    user_repository = UserRepository(database_session)
    user = user_repository.create(username="overview-user")
    other_user = user_repository.create(username="overview-other-user")
    profile_repository = ProfileRepository(database_session)
    profile = profile_repository.create(
        "overview-profile",
        AccessProfile(
            default_duration="1h",
            maximum_duration="8h",
            networks=[IPv4Network(address="10.0.0.0/24")],
        ),
    )
    other_profile = profile_repository.create(
        "other-overview-profile",
        AccessProfile(
            default_duration="1h",
            maximum_duration="8h",
            networks=[IPv4Network(address="192.168.0.0/24")],
        ),
    )
    assignment = profile_repository.assign(user, profile)
    other_assignment = profile_repository.assign(other_user, other_profile)
    device = DeviceRepository(database_session).add(
        Device(user_id=user.id, name="my-device", public_key="my-public-key")
    )
    other_device = DeviceRepository(database_session).add(
        Device(
            user_id=other_user.id,
            name="other-device",
            public_key="other-public-key",
        )
    )
    database_session.add(
        Lease(
            device_id=device.id,
            user_id=user.id,
            profile_user_id=assignment.id,
            ended_at=utcnow() + timedelta(hours=1),
        )
    )
    database_session.add(
        Lease(
            device_id=other_device.id,
            user_id=other_user.id,
            profile_user_id=other_assignment.id,
            ended_at=utcnow() + timedelta(hours=1),
        )
    )
    database_session.commit()

    manager = cast(AuthManager, app.extensions["auth_manager"])
    token = manager.session_service.create(str(user.id))
    response = app.test_client().get(
        "/api/v1/users/me/overview",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    assert response.headers["Cache-Control"] == "no-store"
    payload = cast(dict[str, object], response.get_json())
    assert cast(dict[str, object], payload["user"])["id"] == str(user.id)
    devices = cast(list[dict[str, object]], payload["devices"])
    assert [item["name"] for item in devices] == ["my-device"]
    assert "public_key" not in devices[0]
    leases = cast(list[dict[str, object]], payload["leases"])
    assert len(leases) == 1
    assert leases[0]["device_id"] == device.id
    assert leases[0]["status"] == "active"
    profiles = cast(list[dict[str, object]], payload["profiles"])
    assert len(profiles) == 1
    assert profiles[0]["name"] == "overview-profile"
    assert profiles[0]["policy"] == {
        "default_duration": "1h",
        "maximum_duration": "8h",
        "networks": ["10.0.0.0/24"],
    }


def test_logout_revokes_only_the_current_session(app: Flask) -> None:
    """Logout revokes the request token but leaves other user sessions active."""
    manager = cast(AuthManager, app.extensions["auth_manager"])
    username = cast(str, app.config["TEST_ADMIN_USERNAME"])
    user = manager.user_service.get_by_username(username)
    assert user is not None
    first_token = manager.session_service.create(str(user.id))
    second_token = manager.session_service.create(str(user.id))

    response = app.test_client().post(
        "/api/v1/auth/logout",
        headers={"Authorization": f"Bearer {first_token}"},
    )

    assert response.status_code == 204
    assert response.headers["Cache-Control"] == "no-store"
    assert manager.get_current_user(first_token) is None
    assert manager.get_current_user(second_token) is not None


def test_current_user_and_logout_require_authentication(app: Flask) -> None:
    """Both session endpoints reject missing or invalid bearer credentials."""
    client = app.test_client()
    assert client.get("/api/v1/users/me").status_code == 401
    assert client.get("/api/v1/users/me/overview").status_code == 401
    invalid_headers = {"Authorization": "Bearer invalid"}
    assert client.get("/api/v1/users/me", headers=invalid_headers).status_code == 401
    assert client.get(
        "/api/v1/users/me/overview", headers=invalid_headers
    ).status_code == 401
    assert client.post("/api/v1/auth/logout", headers=invalid_headers).status_code == 401


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
