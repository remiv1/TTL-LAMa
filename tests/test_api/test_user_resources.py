"""Tests for self-service device and lease API routes."""

from datetime import datetime, timedelta, timezone
import logging
from typing import cast
from ipaddress import IPv4Network
from unittest.mock import Mock

from flask import Flask
import pytest
from sqlalchemy.exc import IntegrityError

from api.common.repositories import (
    DeviceRepository,
    LeaseRepository,
    ProfileRepository,
    UserRepository,
)
from api.common.db_objects.devices import Device
from api.common.db_objects.leases import Lease
from api.common.db_objects.lease_provisioning import LeaseProvisioning
from api.common.db_objects.profiles import Profile
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

    second_device = client.post(
        "/api/v1/users/me/devices",
        json={"name": "personal-tablet", "public_key": "second-public-key"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert second_device.status_code == 201

    listed = client.get(
        "/api/v1/users/me/devices",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert listed.status_code == 200
    assert [row["id"] for row in cast(list[dict[str, object]], listed.get_json())] == [
        device_id,
        cast(dict[str, object], second_device.get_json())["id"],
    ]

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


def test_revoking_device_revokes_its_active_leases(app: Flask) -> None:
    """Blocking a device revokes its leases and queues backend removal."""
    session = app.extensions["database_config"].session()
    user = UserRepository(session).create(username="device-lease-owner")
    device = DeviceRepository(session).create(str(user.id), "lease-device", "lease-device-key")
    profile_repository = ProfileRepository(session)
    profile = profile_repository.create(
        "device-lease-profile",
        AccessProfile(
            default_duration="1h",
            maximum_duration="2h",
            lease_target="wg0",
            networks=[IPv4Network("10.44.0.0/24")],
        ),
    )
    profile_repository.assign(user, profile)
    lease = LeaseRepository(session).create(
        user_id=str(user.id), device_id=device.id, profile_id=profile.id,
    )
    lease_id, device_id = lease.id, device.id
    session.commit()

    DeviceRepository(session).block(DeviceRepository(session).get(device_id))
    session.commit()

    session.expire_all()
    assert session.get(Lease, lease_id).revoked_at is not None
    assert session.get(LeaseProvisioning, lease_id).state == "pending_delete"


@pytest.mark.usefixtures("running_lease_scheduler")
def test_user_lease_routes_apply_assignment_and_duration_policy(
    app: Flask,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Lease creation uses an assigned profile's default and maximum durations."""
    caplog.set_level(logging.INFO)
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
            lease_target="wg0",
            networks=[IPv4Network(address="10.0.0.0/24")],
        ),
    )
    assignment = profile_repository.assign(user, profile)
    device = DeviceRepository(database_session).create(
        user_id, "self-lease-device", "lease-public-key"
    )
    database_session.commit()
    device_id, profile_id, assignment_id = device.id, profile.id, assignment.id
    client = app.test_client()
    headers = {"Authorization": f"Bearer {token}"}

    before = datetime.now(timezone.utc)
    created = client.post(
        "/api/v1/users/me/leases",
        json={"device_id": device_id, "profile_id": profile_id},
        headers=headers,
    )
    after = datetime.now(timezone.utc)

    assert created.status_code == 201
    assert any(
        getattr(record, "operation", None) == "lease.create"
        and "succeeded" in record.getMessage()
        for record in caplog.records
    )
    payload = cast(dict[str, object], created.get_json())
    assert payload["user_id"] == user_id
    assert payload["profile_user_id"] == assignment_id
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
    assert any(
        getattr(record, "operation", None) == "lease.revoke"
        and "failed" in record.getMessage()
        for record in caplog.records
    )

    too_long = client.post(
        "/api/v1/users/me/leases",
        json={"device_id": device_id, "profile_id": profile_id, "duration": "3h"},
        headers=headers,
    )
    assert too_long.status_code == 409

    revoked = client.post(
        f"/api/v1/users/me/leases/{lease_id}/revoke",
        headers=headers,
    )
    assert revoked.status_code == 200
    assert cast(dict[str, object], revoked.get_json())["status"] == "revoked"
    assert any(
        getattr(record, "operation", None) == "lease.revoke"
        and "succeeded" in record.getMessage()
        for record in caplog.records
    )


def test_user_lease_creation_rejects_unowned_resources(
    app: Flask,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Lease creation cannot use another user's device or an unassigned profile."""
    caplog.set_level(logging.WARNING)
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
            lease_target="wg0",
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
    assert any(
        getattr(record, "operation", None) == "lease.create"
        and "failed" in record.getMessage()
        for record in caplog.records
    )


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


def test_database_rejects_duplicate_device_public_keys(app: Flask) -> None:
    """The database enforces global uniqueness for device public keys."""
    user_id, _ = _create_user_token(app, "duplicate-key-owner")
    session = app.extensions["database_config"].session()
    session.add(Device(user_id=user_id, name="first-device", public_key="same-key"))
    session.flush()
    session.add(Device(user_id=user_id, name="second-device", public_key="same-key"))

    with pytest.raises(IntegrityError):
        session.flush()
    session.rollback()


def test_database_rejects_duplicate_profile_names(app: Flask) -> None:
    """The database enforces global uniqueness for profile names."""
    session = app.extensions["database_config"].session()
    session.add(Profile(name="same-profile"))
    session.flush()
    session.add(Profile(name="same-profile"))

    with pytest.raises(IntegrityError):
        session.flush()
    session.rollback()


def test_lease_creation_reports_ssh_failure(
    app: Flask,
    running_lease_scheduler: Mock,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """The API reports a failed remote application and revokes the stored bail."""
    monkeypatch.setenv("TTL_LAMA_PROVISIONING_WAIT_SECONDS", "2")
    secret = "ssh-error-secret-sentinel"
    running_lease_scheduler.grant.side_effect = OSError(secret)
    caplog.set_level(logging.INFO)
    user_id, token = _create_user_token(app, "failed-vpn-user")
    session = app.extensions["database_config"].session()
    user = UserRepository(session).get(user_id)
    profiles = ProfileRepository(session)
    profile = profiles.create("failed-vpn-profile", AccessProfile(
        default_duration="1h", maximum_duration="2h", lease_target="wg-failure",
        networks=[IPv4Network("10.124.0.0/24")],
    ))
    profiles.assign(user, profile)
    device = DeviceRepository(session).create(user_id, "failed-vpn-device", "failure-key")
    device_id, profile_id = device.id, profile.id
    session.commit()
    response = app.test_client().post(
        "/api/v1/users/me/leases",
        json={"device_id": device_id, "profile_id": profile_id},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 503
    running_lease_scheduler.grant.assert_called_once()
    lease_id = response.get_json()["lease_id"]
    session = app.extensions["database_config"].session()
    lease = LeaseRepository(session).get(lease_id)
    assert lease.revoked_at is not None
    assert session.get(LeaseProvisioning, lease_id).error == "apply_failed"
    assert any(
        getattr(record, "operation", None) == "lease.apply"
        and "failed" in record.getMessage()
        for record in caplog.records
    )
    assert secret not in " ".join(record.getMessage() for record in caplog.records)


def test_lease_creation_timeout_requests_compensation(
    app: Flask, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A scheduler timeout fails the API request and reserves the uncertain peer."""
    monkeypatch.setenv("TTL_LAMA_PROVISIONING_WAIT_SECONDS", "0.02")
    user_id, token = _create_user_token(app, "timeout-vpn-user")
    session = app.extensions["database_config"].session()
    user = UserRepository(session).get(user_id)
    profiles = ProfileRepository(session)
    profile = profiles.create("timeout-vpn-profile", AccessProfile(
        default_duration="1h", maximum_duration="2h", lease_target="wg-timeout",
        networks=[IPv4Network("10.125.0.0/24")],
    ))
    profiles.assign(user, profile)
    device = DeviceRepository(session).create(user_id, "timeout-device", "timeout-key")
    device_id, profile_id = device.id, profile.id
    session.commit()
    response = app.test_client().post(
        "/api/v1/users/me/leases",
        json={"device_id": device_id, "profile_id": profile_id},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 503
    session = app.extensions["database_config"].session()
    record = session.get(LeaseProvisioning, response.get_json()["lease_id"])
    assert record.state == "pending_delete"
    assert record.error == "apply_failed"
