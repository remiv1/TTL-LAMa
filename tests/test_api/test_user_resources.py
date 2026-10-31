"""Tests for self-service device and lease API routes."""

from datetime import datetime, timedelta, timezone
from typing import cast
from ipaddress import IPv4Network

from flask import Flask

from api.common.repositories import DeviceRepository, ProfileRepository, UserRepository
from api.config.c_profiles import AccessProfile
from auth.manager import AuthManager


def _create_user_token(app: Flask, username: str) -> tuple[str, str]:
    """Create a test user and its bearer token."""
    database_session = app.extensions["database_config"].session()
    user = UserRepository(database_session).create(username=username)
    database_session.commit()
    manager = cast(AuthManager, app.extensions["auth_manager"])
    return str(user.id), manager.session_service.create(str(user.id))


def test_user_device_routes_are_scoped_to_the_owner(app: Flask) -> None:
    """Users can create and revoke devices but cannot read another user's device."""
    user_id, token = _create_user_token(app, "self-device-owner")
    _, other_token = _create_user_token(app, "other-device-owner")
    client = app.test_client()

    response = client.post(
        "/api/v1/users/me/devices",
        json={"name": "personal-laptop", "public_key": "public-key"},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 201, response.get_json()
    assert response.headers["Cache-Control"] == "no-store"
    payload = cast(dict[str, object], response.get_json())
    device_id = cast(int, payload["id"])
    assert payload["user_id"] == user_id
    assert payload["public_key"] == "public-key"

    listed = client.get(
        "/api/v1/users/me/devices",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert listed.status_code == 200
    assert [row["id"] for row in cast(list[dict[str, object]], listed.get_json())] == [device_id]

    own_device = client.get(
        f"/api/v1/users/me/devices/{device_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert own_device.status_code == 200
    other_device = client.get(
        f"/api/v1/users/me/devices/{device_id}",
        headers={"Authorization": f"Bearer {other_token}"},
    )
    assert other_device.status_code == 404
    other_delete = client.delete(
        f"/api/v1/users/me/devices/{device_id}",
        headers={"Authorization": f"Bearer {other_token}"},
    )
    assert other_delete.status_code == 404

    deleted = client.delete(
        f"/api/v1/users/me/devices/{device_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert deleted.status_code == 204
    database_session = app.extensions["database_config"].session()
    assert DeviceRepository(database_session).get(device_id).revoked_at is not None
    assert client.get("/api/v1/users/me/devices").status_code == 401


def test_user_lease_routes_apply_assignment_and_duration_policy(app: Flask) -> None:
    """Lease creation uses an assigned profile's default and maximum durations."""
    user_id, token = _create_user_token(app, "self-lease-owner")
    _, other_token = _create_user_token(app, "other-lease-owner")
    database_session = app.extensions["database_config"].session()
    user = UserRepository(database_session).get(user_id)
    profile_repository = ProfileRepository(database_session)
    profile = profile_repository.create(
        "self-lease-profile",
        AccessProfile(
            default_duration="1h",
            maximum_duration="2h",
            networks=[IPv4Network(address="10.0.0.0/24")],
        ),
    )
    assignment = profile_repository.assign(user, profile)
    device = DeviceRepository(database_session).create(
        user_id, "self-lease-device", "lease-public-key"
    )
    database_session.commit()
    client = app.test_client()
    headers = {"Authorization": f"Bearer {token}"}

    before = datetime.now(timezone.utc)
    created = client.post(
        "/api/v1/users/me/leases",
        json={"device_id": device.id, "profile_id": profile.id},
        headers=headers,
    )
    after = datetime.now(timezone.utc)

    assert created.status_code == 201
    payload = cast(dict[str, object], created.get_json())
    assert payload["user_id"] == user_id
    assert payload["profile_user_id"] == assignment.id
    assert payload["status"] == "active"
    ended_at = datetime.fromisoformat(cast(str, payload["ended_at"]))
    assert before + timedelta(minutes=59) < ended_at < after + timedelta(hours=1, minutes=1)

    lease_id = cast(int, payload["id"])
    listed = client.get("/api/v1/users/me/leases", headers=headers)
    assert listed.status_code == 200
    assert [row["id"] for row in cast(list[dict[str, object]], listed.get_json())] == [lease_id]
    assert client.get(
        f"/api/v1/users/me/leases/{lease_id}", headers=headers
    ).status_code == 200
    assert client.get(
        f"/api/v1/users/me/leases/{lease_id}",
        headers={"Authorization": f"Bearer {other_token}"},
    ).status_code == 404
    other_revoke = client.post(
        f"/api/v1/users/me/leases/{lease_id}/revoke",
        headers={"Authorization": f"Bearer {other_token}"},
    )
    assert other_revoke.status_code == 404

    too_long = client.post(
        "/api/v1/users/me/leases",
        json={"device_id": device.id, "profile_id": profile.id, "duration": "3h"},
        headers=headers,
    )
    assert too_long.status_code == 409

    revoked = client.post(
        f"/api/v1/users/me/leases/{lease_id}/revoke",
        headers=headers,
    )
    assert revoked.status_code == 200
    assert cast(dict[str, object], revoked.get_json())["status"] == "revoked"


def test_user_lease_creation_rejects_unowned_resources(app: Flask) -> None:
    """Lease creation cannot use another user's device or an unassigned profile."""
    _, token = _create_user_token(app, "unassigned-lease-user")
    other_user_id, _ = _create_user_token(app, "resource-owner")
    database_session = app.extensions["database_config"].session()
    device = DeviceRepository(database_session).create(
        other_user_id, "other-device", "other-public-key"
    )
    profile = ProfileRepository(database_session).create(
        "unassigned-profile",
        AccessProfile(
            default_duration="1h",
            maximum_duration="2h",
            networks=[IPv4Network(address="10.0.0.0/24")],
        ),
    )
    database_session.commit()
    response = app.test_client().post(
        "/api/v1/users/me/leases",
        json={"device_id": device.id, "profile_id": profile.id},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 404


def test_user_device_creation_reports_invalid_payload_as_json(app: Flask) -> None:
    """Invalid device payloads use the self-service JSON error contract."""
    _, token = _create_user_token(app, "invalid-device-payload-user")
    response = app.test_client().post(
        "/api/v1/users/me/devices",
        json={"name": "missing-public-key"},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 400
    assert response.is_json
    assert response.get_json()["error"] == "Invalid input"
