"""Tests for the web interface and its session workflows."""

import re
from typing import cast
from ipaddress import IPv4Network

from flask import Flask
from flask.testing import FlaskClient

from api.common.repositories import (
    DeviceRepository,
    LeaseRepository,
    ProfileRepository,
    UserRepository,
)
from api.common.repositories.leases import utcnow
from api.config.c_profiles import AccessProfile


def _csrf_headers(client: FlaskClient) -> dict[str, str]:
    response = client.get("/api/v1/csrf")
    payload = cast(dict[str, object], response.get_json())
    token = payload.get("csrf_token")
    assert isinstance(token, str)
    return {"X-CSRFToken": token}


def test_homepage_defaults_to_english_and_uses_local_assets(app: Flask) -> None:
    """Test that the homepage defaults to English and uses local assets."""
    client = app.test_client()

    response = client.get("/")
    body = response.get_data(as_text=True)

    assert response.status_code == 200
    assert response.mimetype == "text/html"
    assert '<html lang="en">' in body
    assert "Temporary access. Automatic revocation." in body
    assert "/web/static/css/main.css" in body
    assert "/web/static/js/htmx.min.js" in body
    assert 'name="htmx-config"' in body
    assert "includeIndicatorStyles" in body
    assert "<script>" not in body
    assert " style=" not in body

    stylesheet = client.get("/web/static/css/main.css")
    htmx = client.get("/web/static/js/htmx.min.js")
    assert stylesheet.status_code == 200
    assert htmx.status_code == 200

    fragment = client.get("/devices", headers={"HX-Request": "true"})
    fragment_body = fragment.get_data(as_text=True)
    assert fragment.status_code == 200
    assert 'id="main-content"' not in fragment_body
    assert "<header" not in fragment_body
    assert "<footer" not in fragment_body
    assert "not available yet" in fragment_body


def test_language_choice_is_saved_and_untrusted_redirect_is_rejected(
    app: Flask,
) -> None:
    """Test that the language choice is saved and untrusted redirects are rejected."""
    client = app.test_client()
    response = client.post(
        "/language",
        data={"language": "fr", "next": "//example.invalid"},
        headers=_csrf_headers(client),
    )

    assert response.status_code == 303
    assert response.headers["Location"] == "/"
    backslash_response = client.post(
        "/language",
        data={"language": "fr", "next": "/\\example.invalid"},
        headers=_csrf_headers(client),
    )
    assert backslash_response.headers["Location"] == "/"
    homepage = client.get("/").get_data(as_text=True)
    assert '<html lang="fr">' in homepage
    assert "Accès temporaire. Révocation automatique." in homepage


def test_navigation_is_keyboard_operable_and_sections_are_explicitly_pending(
    app: Flask,
) -> None:
    """Test that the navigation is keyboard operable and sections are explicitly pending."""
    client = app.test_client()
    homepage = client.get("/").get_data(as_text=True)

    assert 'type="button" data-menu-toggle' in homepage
    assert 'aria-controls="main-menu" aria-expanded="false"' in homepage
    assert 'id="main-menu"' in homepage

    for path in ("/devices", "/leases", "/profiles"):
        response = client.get(path)
        assert response.status_code == 200
        assert "not available yet" in response.get_data(as_text=True)


def test_authenticated_device_page_shows_creation_form_and_owned_devices(
    app: Flask,
) -> None:
    """The signed-in user can create a device and sees only their own inventory."""
    database_session = app.extensions["database_config"].session()
    user = UserRepository(database_session).create(username="device-page-user")
    device = DeviceRepository(database_session).create(
        str(user.id), "existing-laptop", "existing-public-key"
    )
    revoked_device = DeviceRepository(database_session).create(
        str(user.id), "revoked-device", "revoked-public-key"
    )
    DeviceRepository(database_session).block(revoked_device)
    database_session.commit()
    manager = app.extensions["auth_manager"]
    token = manager.session_service.create(str(user.id))
    client = app.test_client()
    client.set_cookie(cast(str, app.config["AUTH_COOKIE_NAME"]), token)

    response = client.get("/devices")
    body = response.get_data(as_text=True)

    assert response.status_code == 200
    assert 'data-device-form' in body
    assert 'data-endpoint="/api/v1/users/me/devices"' in body
    assert 'data-device-workspace' in body
    assert 'data-device-select' in body
    assert 'aria-pressed="true"' in body
    assert 'data-device-dialog' in body
    assert 'data-delete-dialog' in body
    assert "Generate a key pair" in body
    assert "existing-laptop" in body
    assert f"#{device.id}" in body
    assert "existing-public-key" in body
    assert "revoked-device" not in body
    assert "Private key" in body
    assert 'name="private_key"' not in body

    created = client.post(
        "/api/v1/users/me/devices",
        json={"name": "browser-device", "public_key": "browser-public-key"},
        headers=_csrf_headers(client),
    )
    assert created.status_code == 201
    assert created.get_json()["name"] == "browser-device"


def test_authenticated_device_page_shows_empty_state(app: Flask) -> None:
    """An authenticated user without active devices sees the empty state."""
    database_session = app.extensions["database_config"].session()
    user = UserRepository(database_session).create(username="empty-device-page-user")
    database_session.commit()
    manager = app.extensions["auth_manager"]
    token = manager.session_service.create(str(user.id))
    client = app.test_client()
    client.set_cookie(cast(str, app.config["AUTH_COOKIE_NAME"]), token)

    response = client.get("/devices")
    body = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "No devices yet." in body
    assert re.search(r'data-device-detail[^>]*\shidden>', body)


def test_authenticated_profiles_page_shows_assigned_profiles_and_policy(
    app: Flask,
) -> None:
    """The signed-in user sees assigned profiles and not another user's profiles."""
    database_session = app.extensions["database_config"].session()
    user = UserRepository(database_session).create(username="profile-page-user")
    repository = ProfileRepository(database_session)
    assigned_profile = repository.create(
        "web-page-assigned-profile",
        AccessProfile(
            default_duration="1h",
            maximum_duration="4h",
            lease_target="wg0",
            networks=[IPv4Network("10.20.0.0/16")],
        ),
    )
    unassigned_profile = repository.create(
        "web-page-unassigned-profile",
        AccessProfile(
            default_duration="30m",
            maximum_duration="2h",
            lease_target="wg0",
            networks=[IPv4Network("192.168.10.0/24")],
        ),
    )
    repository.assign(user, assigned_profile)
    database_session.commit()
    manager = app.extensions["auth_manager"]
    token = manager.session_service.create(str(user.id))
    client = app.test_client()
    client.set_cookie(cast(str, app.config["AUTH_COOKIE_NAME"]), token)

    response = client.get("/profiles")
    body = response.get_data(as_text=True)

    assert response.status_code == 200
    assert assigned_profile.name in body
    assert f"#{assigned_profile.id}" in body
    assert "1h" in body
    assert "4h" in body
    assert "10.20.0.0/16" in body
    assert unassigned_profile.name not in body

    client.set_cookie("ttl_lama_language", "fr")
    french_body = client.get("/profiles").get_data(as_text=True)
    assert "Durée par défaut" in french_body
    assert "Réseaux autorisés" in french_body


def test_authenticated_profiles_page_shows_empty_state(app: Flask) -> None:
    """An authenticated user without assignments sees the translated empty state."""
    database_session = app.extensions["database_config"].session()
    user = UserRepository(database_session).create(username="empty-profile-page-user")
    database_session.commit()
    manager = app.extensions["auth_manager"]
    token = manager.session_service.create(str(user.id))
    client = app.test_client()
    client.set_cookie(cast(str, app.config["AUTH_COOKIE_NAME"]), token)
    client.set_cookie("ttl_lama_language", "fr")

    response = client.get("/profiles")

    assert response.status_code == 200
    assert "Aucun profil d’accès n’est attribué à votre compte" in response.get_data(
        as_text=True
    )


def test_authenticated_leases_page_groups_statuses_and_limits_creation_options(
    app: Flask,
) -> None:
    """The lease page groups history and offers only currently eligible choices."""
    database_session = app.extensions["database_config"].session()
    user = UserRepository(database_session).create(username="lease-page-user")
    device_repository = DeviceRepository(database_session)
    device = device_repository.create(str(user.id), "lease-laptop", "lease-public-key")
    revoked_device = device_repository.create(
        str(user.id), "blocked-lease-device", "blocked-public-key"
    )
    device_repository.block(revoked_device)
    profile_repository = ProfileRepository(database_session)
    assigned_profile = profile_repository.create(
        "lease-page-assigned-profile",
        AccessProfile(
            default_duration="1h",
            maximum_duration="4h",
            lease_target="wg0",
            networks=[IPv4Network("10.30.0.0/16")],
        ),
    )
    unassigned_profile = profile_repository.create(
        "lease-page-unassigned-profile",
        AccessProfile(
            default_duration="30m",
            maximum_duration="2h",
            lease_target="wg0",
            networks=[IPv4Network("192.168.30.0/24")],
        ),
    )
    profile_repository.assign(user, assigned_profile)
    lease_repository = LeaseRepository(database_session)
    active_lease = lease_repository.create(
        user_id=str(user.id),
        device_id=device.id,
        profile_id=assigned_profile.id,
    )
    expired_lease = lease_repository.create(
        user_id=str(user.id),
        device_id=device.id,
        profile_id=assigned_profile.id,
    )
    expired_lease.ended_at = utcnow()
    revoked_lease = lease_repository.create(
        user_id=str(user.id),
        device_id=device.id,
        profile_id=assigned_profile.id,
    )
    lease_repository.revoke(revoked_lease)
    database_session.commit()
    manager = app.extensions["auth_manager"]
    token = manager.session_service.create(str(user.id))
    client = app.test_client()
    client.set_cookie(cast(str, app.config["AUTH_COOKIE_NAME"]), token)

    response = client.get("/leases")
    body = response.get_data(as_text=True)

    assert response.status_code == 200
    assert 'data-lease-workspace' in body
    assert 'data-status="active"' in body
    assert 'data-status="expired"' in body
    assert 'data-status="revoked"' in body
    assert 'data-revoked-section' in body
    assert not re.search(r'data-revoked-section[^>]*\sopen(?:\s|>)', body)
    assert device.name in body
    assert revoked_device.name not in body
    assert assigned_profile.name in body
    assert unassigned_profile.name not in body
    assert "1h" in body
    assert "4h" in body
    assert "10.30.0.0/16" in body
    assert f'#{active_lease.id}' in body
    assert f'#{expired_lease.id}' in body
    assert f'#{revoked_lease.id}' in body
    assert "Revoked leases" in body


def test_authenticated_leases_page_disables_creation_without_eligible_resources(
    app: Flask,
) -> None:
    """The empty lease page explains why creation is unavailable."""
    database_session = app.extensions["database_config"].session()
    user = UserRepository(database_session).create(username="empty-lease-page-user")
    database_session.commit()
    manager = app.extensions["auth_manager"]
    token = manager.session_service.create(str(user.id))
    client = app.test_client()
    client.set_cookie(cast(str, app.config["AUTH_COOKIE_NAME"]), token)

    response = client.get("/leases")
    body = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "No access leases yet." in body
    assert "Add an active device before requesting access." in body
    assert "No eligible assigned access profiles are available." in body
    assert re.search(r'data-open-lease-dialog[^>]*\sdisabled(?:\s|>)', body)


def test_authenticated_lease_creation_and_revocation_use_csrf_protected_api(
    app: Flask,
) -> None:
    """A signed-in user can create a default-duration lease and revoke it."""
    database_session = app.extensions["database_config"].session()
    user = UserRepository(database_session).create(username="lease-mutation-user")
    device = DeviceRepository(database_session).create(
        str(user.id), "lease-mutation-laptop", "lease-mutation-public-key"
    )
    profile_repository = ProfileRepository(database_session)
    profile = profile_repository.create(
        "lease-mutation-profile",
        AccessProfile(
            default_duration="1h",
            maximum_duration="4h",
            lease_target="wg0",
            networks=[IPv4Network("10.40.0.0/16")],
        ),
    )
    profile_repository.assign(user, profile)
    database_session.commit()
    manager = app.extensions["auth_manager"]
    token = manager.session_service.create(str(user.id))
    client = app.test_client()
    client.set_cookie(cast(str, app.config["AUTH_COOKIE_NAME"]), token)
    csrf_headers = _csrf_headers(client)

    created = client.post(
        "/api/v1/users/me/leases",
        json={"device_id": device.id, "profile_id": profile.id},
        headers=csrf_headers,
    )

    assert created.status_code == 201
    payload = cast(dict[str, object], created.get_json())
    assert payload["status"] == "active"
    assert payload["device_id"] == device.id
    assert payload["profile_id"] == profile.id
    assert payload["ended_at"]

    lease_id = cast(int, payload["id"])
    revoked = client.post(
        f"/api/v1/users/me/leases/{lease_id}/revoke",
        headers=csrf_headers,
    )
    assert revoked.status_code == 200
    assert revoked.get_json()["status"] == "revoked"

    body = client.get("/leases").get_data(as_text=True)
    assert f'data-lease-id="{lease_id}" data-status="revoked"' in body
    assert "Revoked leases" in body


def test_internal_login_account_status_and_logout(app: Flask) -> None:
    """Test the internal login, account status, and logout functionality."""
    client = app.test_client()
    username = cast(str, app.config["TEST_ADMIN_USERNAME"])

    login_page = client.get("/login")
    assert login_page.status_code == 200
    assert 'name="csrf_token"' in login_page.get_data(as_text=True)

    login = client.post(
        "/auth/login",
        data={
            "username": username,
            "password": "correct-horse-battery",
        },
        headers=_csrf_headers(client),
    )
    assert login.status_code == 303
    assert login.headers["Location"] == "/"

    account = client.get("/account")
    assert account.status_code == 200
    assert username in account.get_data(as_text=True)
    assert "Your session is active." in account.get_data(as_text=True)

    logout = client.post("/logout", headers=_csrf_headers(client))
    assert logout.status_code == 303
    assert logout.headers["Location"] == "/"
    assert any(
        value.startswith(f"{app.config['AUTH_COOKIE_NAME']}=")
        and "Max-Age=0" in value
        for value in logout.headers.getlist("Set-Cookie")
    )
    assert client.get("/account").status_code == 302


def test_security_policy_allows_only_local_ui_resources(app: Flask) -> None:
    """Test that the security policy allows only local UI resources."""
    response = app.test_client().get("/")
    policy = response.headers["Content-Security-Policy"]

    assert "script-src 'self'" in policy
    assert "style-src 'self'" in policy
    assert "connect-src 'self'" in policy
    assert "unsafe-inline" not in policy
