"""Administrative contracts, authorization, persistence and revocation tests."""
from __future__ import annotations

from dataclasses import dataclass
from collections.abc import Mapping
from datetime import timedelta
from typing import cast
from uuid import uuid4

import pytest
from flask import Flask
from flask.testing import FlaskClient
from pydantic import TypeAdapter
from sqlalchemy import select
from werkzeug.test import TestResponse

from auth.backends import AuthBackend
from api.common.db_objects.devices import Device
from api.common.db_objects.leases import Lease
from api.common.db_objects.profiles import ProfileUser
from api.common.db_objects.profiles import Profile
from api.common.db_objects.users import User
from api.common.repositories import ProfileRepository, UserRepository
from api.common.repositories.leases import utcnow
from api.bootstrap import create_app
from api.config import DatabaseSettings, FlaskSettings
from api.config.c_profiles import AccessProfile, AccessProfiles

PREFIX = "/api/v1/admin"
POLICY = {
    "default_duration": "1h",
    "maximum_duration": "8h",
    "networks": ["10.0.0.0/24"],
}


def json_object(response: TestResponse) -> dict[str, object]:
    """Verify that a resource response is a JSON object."""
    return TypeAdapter(dict[str, object]).validate_python(response.get_json())


def json_rows(response: TestResponse) -> list[dict[str, object]]:
    """Verify the exact list response shape."""
    return TypeAdapter(list[dict[str, object]]).validate_python(response.get_json())


@dataclass
class Domain:   # pylint: disable=R0902
    """A real authenticated client and a connected domain graph."""
    app: Flask
    client: FlaskClient
    headers: dict[str, str]
    user_headers: dict[str, str]
    user_id: str
    profile_id: int
    device_id: int
    lease_id: int
    expired_id: int

    def path(self, resource: str) -> str:
        """Prefix an administrative resource path."""
        return f"{PREFIX}/{resource}"


@pytest.mark.parametrize("role", ["anonymous", "user", "invalid", "malformed"])
def test_every_admin_route_is_protected(domain: Domain, role: str) -> None:
    """Every registered method rejects missing or non-admin authentication."""
    headers = {
        "anonymous": {},
        "user": domain.user_headers,
        "invalid": {"Authorization": "Bearer invalid"},
        "malformed": {"Authorization": "Basic invalid"},
    }[role]
    for rule in domain.app.url_map.iter_rules():
        if not rule.endpoint.startswith("api_v1.admin."):
            continue
        path = str(rule).replace("<uuid:user_id>", domain.user_id)
        path = path.replace("<int:profile_id>", str(domain.profile_id))
        path = path.replace("<int:device_id>", str(domain.device_id))
        path = path.replace("<int:lease_id>", str(domain.lease_id))
        for method in rule.methods or ():
            response = domain.client.open(path, method=method, headers=headers)
            expected = 403 if role == "user" else 401
            # Unsafe requests without a well-formed bearer header need CSRF first.
            if role in {"anonymous", "malformed"} and method not in {"GET", "HEAD", "OPTIONS"}:
                expected = 400
            assert response.status_code == expected, (method, path, response.get_data())


def test_admin_read_all_resources_and_filters(domain: Domain) -> None:
    """Exercise all documented filter relationships, including intersections."""
    cases = {
        f"users?device={domain.device_id}&lease={domain.lease_id}&profile={domain.profile_id}":
            domain.user_id,
        f"devices?lease={domain.lease_id}&profile={domain.profile_id}": domain.device_id,
        f"leases?user={domain.user_id}&device={domain.device_id}"
        f"&profile={domain.profile_id}&status=active": domain.lease_id,
        f"profiles?user={domain.user_id}&device={domain.device_id}&lease={domain.lease_id}":
            domain.profile_id,
        f"users/{domain.user_id}/profiles": domain.profile_id,
    }
    for path, identifier in cases.items():
        response = domain.client.get(domain.path(path), headers=domain.headers)
        assert response.status_code == 200
        assert [row["id"] for row in json_rows(response)] == [identifier]
        assert response.headers["Cache-Control"] == "no-store"
    for resource, identifier in (
        ("users", domain.user_id), ("devices", domain.device_id),
        ("leases", domain.lease_id), ("profiles", domain.profile_id),
    ):
        response = domain.client.get(
            domain.path(f"{resource}/{identifier}"),
            headers=domain.headers,
        )
        assert response.status_code == 200
        assert json_object(response)["id"] == identifier
    response = domain.client.get(
        domain.path(f"leases?device={domain.device_id}&status=expired"), headers=domain.headers
    )
    assert [row["id"] for row in json_rows(response)] == [domain.expired_id]


def test_user_crud_password_and_session_invalidation(domain: Domain) -> None:
    """User writes persist and passwords are usable but never returned."""
    username = f"created-{uuid4().hex}"
    password = "test-admin-created-password"
    created = domain.client.post(domain.path("users"), headers=domain.headers, json={
        "username": username, "email": "created@example.test", "password": password,
    })
    assert created.status_code == 201
    identifier = json_object(created)["id"]
    assert isinstance(identifier, str)
    assert "password" not in created.get_data(as_text=True)
    assert "hash_password" not in json_object(created)
    login = domain.client.post("/api/v1/auth", headers={"Authorization": "Bearer unused"},
                               json={"username": username, "password": password})
    assert login.status_code == 200
    user = domain.app.extensions["auth_manager"].user_service.get_by_id(identifier)
    token = domain.app.extensions["auth_manager"].session_service.create(str(user.id))
    updated = domain.client.patch(domain.path(f"users/{identifier}"), headers=domain.headers,
                                  json={"email": None, "password": "replacement-password"})
    assert updated.status_code == 200
    assert json_object(updated)["email"] is None
    assert domain.app.extensions["auth_manager"].get_current_user(token) is None
    deleted = domain.client.delete(domain.path(f"users/{identifier}"), headers=domain.headers)
    assert deleted.status_code == 204
    assert json_object(domain.client.get(
        domain.path(f"users/{identifier}"), headers=domain.headers
    ))["enabled"] is False


def test_user_creation_generates_password_for_internal_auth(domain: Domain) -> None:
    """A generated password is returned once and can authenticate the new user."""
    username = f"generated-{uuid4().hex}"
    created = domain.client.post(
        domain.path("users"),
        headers=domain.headers,
        json={"username": username},
    )

    assert created.status_code == 201
    payload = json_object(created)
    generated_password = payload["generated_password"]
    user = payload["user"]
    assert isinstance(generated_password, str)
    assert generated_password != ""
    assert isinstance(user, dict)
    assert user["username"] == username
    assert "password" not in user
    assert "hash_password" not in user
    stored_user = UserRepository(
        domain.app.extensions["database_config"].session()
    ).get(cast(str, user["id"]))
    assert len(stored_user.credentials) == 1
    assert stored_user.credentials[0].hash_password.startswith("$argon2id$")
    assert stored_user.credentials[0].hash_password != generated_password

    login = domain.client.post(
        "/api/v1/auth",
        headers={"Authorization": "Bearer unused"},
        json={"username": username, "password": generated_password},
    )
    assert login.status_code == 200

    identifier = cast(str, user["id"])
    retrieved = domain.client.get(
        domain.path(f"users/{identifier}"),
        headers=domain.headers,
    )
    assert retrieved.status_code == 200
    assert "generated_password" not in retrieved.get_data(as_text=True)
    assert "hash_password" not in retrieved.get_data(as_text=True)


def test_user_creation_without_internal_backend_does_not_generate_password(
    domain: Domain,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An omitted password creates no internal credential outside internal mode."""
    username = f"external-{uuid4().hex}"
    manager = domain.app.extensions["auth_manager"]
    monkeypatch.setattr(manager, "backend", cast(AuthBackend, object()))

    created = domain.client.post(
        domain.path("users"),
        headers=domain.headers,
        json={"username": username},
    )

    assert created.status_code == 201
    payload = json_object(created)
    assert payload["username"] == username
    assert "generated_password" not in payload
    stored_user = UserRepository(
        domain.app.extensions["database_config"].session()
    ).by_username(username)
    assert stored_user is not None
    assert stored_user.credentials == []


@pytest.mark.parametrize("operation", ["user-delete", "user-disable", "device-delete",
                                      "device-block", "device-key", "profile-delete",
                                      "profile-policy", "unassign", "lease-revoke"])
def test_revocation_cascades_and_preserves_history(domain: Domain, operation: str) -> None:
    """Every access-changing operation invalidates the dependent leases."""
    operations: dict[str, tuple[str, str, dict[str, object] | None]] = {
        "user-delete": ("DELETE", f"users/{domain.user_id}", None),
        "user-disable": ("PATCH", f"users/{domain.user_id}", {"enabled": False}),
        "device-delete": ("DELETE", f"devices/{domain.device_id}", None),
        "device-block": ("POST", f"devices/{domain.device_id}/block", None),
        "device-key": ("PATCH", f"devices/{domain.device_id}", {"public_key": "new-key"}),
        "profile-delete": ("DELETE", f"profiles/{domain.profile_id}", None),
        "profile-policy": ("PATCH", f"profiles/{domain.profile_id}", {"maximum_duration": "2h"}),
        "unassign": ("DELETE", f"users/{domain.user_id}/profiles/{domain.profile_id}", None),
        "lease-revoke": ("POST", f"leases/{domain.lease_id}/revoke", None),
    }
    method, path, data = operations[operation]
    response = domain.client.open(
        domain.path(path),
        method=method,
        headers=domain.headers,
        json=data,
    )
    assert response.status_code in {200, 204}, response.get_data()
    lease = domain.client.get(domain.path(f"leases/{domain.lease_id}"), headers=domain.headers)
    assert lease.status_code == 200
    assert json_object(lease)["status"] == "revoked"
    assert json_object(lease)["revoked_at"] is not None
    revoked_at = json_object(lease)["revoked_at"]
    response = domain.client.post(domain.path(f"leases/{domain.lease_id}/revoke"),
                                  headers=domain.headers)
    assert response.status_code == 200
    assert json_object(response)["revoked_at"] == revoked_at
    if operation.startswith("user-"):
        assert domain.app.extensions["auth_manager"].get_current_user(
            domain.user_headers["Authorization"].split(" ", 1)[1]
        ) is None


def test_device_metadata_does_not_revoke_access(domain: Domain) -> None:
    """Renaming a device does not change its VPN identity."""
    response = domain.client.patch(domain.path(f"devices/{domain.device_id}"),
                                  headers=domain.headers, json={"name": "renamed"})
    assert response.status_code == 200
    assert json_object(response)["name"] == "renamed"
    assert json_object(domain.client.get(
        domain.path(f"leases/{domain.lease_id}"), headers=domain.headers
    ))["status"] == "active"


def test_profile_crud_and_assignment_history(domain: Domain) -> None:
    """Policies persist, assignment is idempotent and reassignment keeps history."""
    name = f"created-profile-{uuid4().hex}"
    response = domain.client.post(domain.path("profiles"), headers=domain.headers,
                                 json={"name": name, **POLICY})
    assert response.status_code == 201
    identifier = json_object(response)["id"]
    assert isinstance(identifier, int)
    assert json_object(response)["policy"] == POLICY
    path = domain.path(f"users/{domain.user_id}/profiles/{identifier}")
    first = domain.client.put(path, headers=domain.headers)
    second = domain.client.put(path, headers=domain.headers)
    assert first.status_code == second.status_code == 200
    assert json_object(first)["id"] == json_object(second)["id"]
    assert domain.client.delete(path, headers=domain.headers).status_code == 204
    assert domain.client.delete(path, headers=domain.headers).status_code == 204
    third = domain.client.put(path, headers=domain.headers)
    assert third.status_code == 200
    assert json_object(third)["id"] != json_object(first)["id"]
    response = domain.client.patch(domain.path(f"profiles/{identifier}"),
                                  headers=domain.headers, json={"name": f"{name}-renamed"})
    assert response.status_code == 200
    assert json_object(response)["policy"] == POLICY
    assert domain.client.delete(domain.path(f"profiles/{identifier}"),
                                headers=domain.headers).status_code == 204
    assert domain.client.put(path, headers=domain.headers).status_code == 409


@pytest.mark.parametrize("method,path,payload", [
    ("POST", "users", {"username": "x", "is_admin": "true"}),
    ("POST", "users", {"username": "x", "password": ""}),
    ("POST", "users", {"username": "x", "sessions": []}),
    ("POST", "users", []),
    ("POST", "profiles", {"name": "x", **POLICY, "networks": ["not-a-network"]}),
    ("POST", "profiles", {"name": "x", **POLICY, "default_duration": "9h"}),
    ("PATCH", "users/{user}", {"enabled": None}),
    ("PATCH", "users/{user}", {}),
    ("PATCH", "devices/{device}", {"user_id": "someone-else"}),
    ("PATCH", "devices/{device}", {"public_key": None}),
    ("PATCH", "profiles/{profile}", {"maximum_duration": "1m"}),
    ("PATCH", "profiles/{profile}", {"networks": []}),
    ("PATCH", "profiles/{profile}", {"revoked_at": None}),
])
def test_invalid_mutations_are_rejected_without_writes(
    domain: Domain, method: str, path: str, payload: object,
) -> None:
    """Strict validation prevents mass assignment and partial invalid policies."""
    path = path.format(user=domain.user_id, device=domain.device_id, profile=domain.profile_id)
    response = domain.client.open(domain.path(path), method=method,
                                  headers=domain.headers, json=payload)
    assert response.status_code == 400, response.get_data()
    lease = domain.client.get(domain.path(f"leases/{domain.lease_id}"), headers=domain.headers)
    assert json_object(lease)["status"] == "active"


@pytest.mark.parametrize("query", [
    "users?profile=nope", "users?device=0", "devices?unknown=1",
    "leases?status=pending", "leases?user=invalid", "profiles?lease=-1",
    "users?profile=1&profile=2",
])
def test_invalid_filters(domain: Domain, query: str) -> None:
    """Reject invalid and ambiguous filters explicitly."""
    assert domain.client.get(domain.path(query), headers=domain.headers).status_code == 400


def test_conflicts_and_missing_resources(domain: Domain) -> None:
    """Conflicts roll back the transaction and leave future requests usable."""
    user = json_object(domain.client.get(
        domain.path(f"users/{domain.user_id}"), headers=domain.headers
    ))
    duplicate = domain.client.post(domain.path("users"), headers=domain.headers,
                                  json={"username": user["username"]})
    assert duplicate.status_code == 409
    profile = json_object(domain.client.get(
        domain.path(f"profiles/{domain.profile_id}"), headers=domain.headers
    ))
    assert domain.client.post(domain.path("profiles"), headers=domain.headers,
                               json={"name": profile["name"], **POLICY}).status_code == 409
    for path in (f"users/{uuid4()}", "devices/2147483647", "leases/2147483647",
                 "profiles/2147483647"):
        response = domain.client.get(domain.path(path), headers=domain.headers)
        assert response.status_code == 404
        assert "error" in json_object(response)


def test_cookie_csrf_and_bearer_precedence(domain: Domain) -> None:
    """Admin cookies need CSRF and cannot rescue a malformed bearer header."""
    token = domain.headers["Authorization"].split(" ", 1)[1]
    config = cast(Mapping[str, object], domain.app.config)
    cookie_name = config["AUTH_COOKIE_NAME"]
    assert isinstance(cookie_name, str)
    domain.client.set_cookie(cookie_name, token)
    path = domain.path(f"devices/{domain.device_id}")
    assert domain.client.patch(path, json={"name": "unsafe"}).status_code == 400
    csrf = json_object(domain.client.get("/api/v1/csrf"))["csrf_token"]
    assert isinstance(csrf, str)
    assert domain.client.patch(path, headers={"X-CSRFToken": csrf},
                                json={"name": "safe"}).status_code == 200
    assert domain.client.get(path, headers={"Authorization": "Basic invalid"}).status_code == 401


def test_privilege_revocation_is_immediate(domain: Domain) -> None:
    """A previously issued admin session cannot bypass a demotion."""
    manager = domain.app.extensions["auth_manager"]
    session = domain.app.extensions["database_config"].session()
    user = session.get(User, domain.user_id)
    assert user is not None
    user.is_admin = True
    session.commit()
    assert domain.client.get(domain.path("users"), headers=domain.user_headers).status_code == 200
    response = domain.client.patch(domain.path(f"users/{domain.user_id}"),
                                  headers=domain.headers, json={"is_admin": False})
    assert response.status_code == 200
    assert manager.get_current_user(domain.user_headers["Authorization"].split(" ", 1)[1]) is None


def test_repository_transactions_and_yaml_seeding(domain: Domain) -> None:
    """Repositories allow rollback and YAML imports never overwrite API edits."""
    database = domain.app.extensions["database_config"]
    session = database.session()
    repository = ProfileRepository(session)
    name = f"configuration-{uuid4().hex}"
    profiles = AccessProfiles.model_validate({"profiles": {name: POLICY}})
    repository.import_missing(profiles)
    profile = repository.list(repository.model.name == name)[0]
    identifier = profile.id
    session.rollback()
    assert session.get(repository.model, identifier) is None
    repository.import_missing(profiles)
    session.commit()
    profile = repository.list(repository.model.name == name)[0]
    repository.set_policy(
        profile,
        AccessProfile.model_validate(
            {
                **POLICY,
                "maximum_duration": "4h",
            },
        )
    )
    session.commit()
    repository.import_missing(profiles)
    session.commit()
    policy = repository.policy(profile)
    assert policy is not None
    assert policy.maximum_duration == "4h"
    repository.delete(profile)
    session.commit()
    repository.import_missing(profiles)
    session.commit()
    assert profile.revoked_at is not None
    assignments = list(session.scalars(select(ProfileUser).where(
        ProfileUser.profile_id == domain.profile_id
    )))
    assert len(assignments) == 1


def test_policy_survives_application_restart(
    domain: Domain, database_settings: DatabaseSettings,
) -> None:
    """Persist API edits across construction of a second application."""
    path = domain.path(f"profiles/{domain.profile_id}")
    response = domain.client.patch(path, headers=domain.headers,
                                   json={"maximum_duration": "3h"})
    assert response.status_code == 200
    config = cast(Mapping[str, object], domain.app.config)
    username = config["TEST_ADMIN_USERNAME"]
    assert isinstance(username, str)
    settings = FlaskSettings(
        AUTH_MODE="internal",
        FLASK_ENV="testing",
        SECRET_KEY="test-secret-key-with-more-than-thirty-two-characters",
        ADMIN_USERNAME=username,
        ADMIN_PASSWORD="correct-horse-battery",
        ENFORCE_SECURE_CONNECTION=False,
        SESSION_COOKIE_SECURE=False,
    )
    restarted = create_app(settings, database_settings)
    try:
        response = restarted.test_client().get(path, headers=domain.headers)
        assert response.status_code == 200
        policy = json_object(response)["policy"]
        assert isinstance(policy, dict)
        assert policy["maximum_duration"] == "3h"
    finally:
        restarted.extensions["database_config"].close()


def test_revoking_one_assignment_keeps_other_users_access(domain: Domain) -> None:
    """Revocation scopes do not spill into another user's leases."""
    session = domain.app.extensions["database_config"].session()
    user = UserRepository(session).create(username=f"other-{uuid4().hex}")
    profile = ProfileRepository(session).get(domain.profile_id)
    assignment = ProfileRepository(session).assign(user, profile)
    device = Device(user_id=str(user.id), name="other", public_key="other-key")
    session.add(device)
    session.flush()
    lease = Lease(
        user_id=str(user.id), device_id=device.id, profile_user_id=assignment.id,
        ended_at=utcnow() + timedelta(hours=1),
    )
    session.add(lease)
    session.commit()
    identifier = lease.id
    response = domain.client.delete(
        domain.path(f"users/{domain.user_id}/profiles/{domain.profile_id}"),
        headers=domain.headers,
    )
    assert response.status_code == 204
    response = domain.client.get(domain.path(f"leases/{identifier}"), headers=domain.headers)
    assert json_object(response)["status"] == "active"


def test_direct_privilege_changes_are_not_cached(domain: Domain) -> None:
    """Authentication refreshes role state even without API session revocation."""
    session = domain.app.extensions["database_config"].session()
    user = session.get(User, domain.user_id)
    assert user is not None
    user.is_admin = True
    session.commit()
    assert domain.client.get(domain.path("users"), headers=domain.user_headers).status_code == 200
    session = domain.app.extensions["database_config"].session()
    user = session.get(User, domain.user_id)
    assert user is not None
    user.is_admin = False
    session.commit()
    assert domain.client.get(domain.path("users"), headers=domain.user_headers).status_code == 403


def test_legacy_profile_can_receive_a_complete_policy(domain: Domain) -> None:
    """Existing SQL profiles remain readable and can acquire a validated policy."""
    session = domain.app.extensions["database_config"].session()
    profile = Profile(name=f"legacy-{uuid4().hex}")
    session.add(profile)
    session.commit()
    path = domain.path(f"profiles/{profile.id}")
    response = domain.client.get(path, headers=domain.headers)
    assert response.status_code == 200
    assert json_object(response)["policy"] is None
    response = domain.client.patch(path, headers=domain.headers,
                                   json={"maximum_duration": "8h"})
    assert response.status_code == 400
    response = domain.client.patch(path, headers=domain.headers, json=POLICY)
    assert response.status_code == 200
    assert json_object(response)["policy"] == POLICY


def test_profile_conflict_rolls_back_policy_and_revocations(domain: Domain) -> None:
    """A later name conflict must roll back earlier policy and lease changes."""
    name = f"conflicting-{uuid4().hex}"
    session = domain.app.extensions["database_config"].session()
    ProfileRepository(session).create(name, AccessProfile.model_validate(POLICY))
    session.commit()
    response = domain.client.patch(
        domain.path(f"profiles/{domain.profile_id}"), headers=domain.headers,
        json={"name": name, "maximum_duration": "4h"},
    )
    assert response.status_code == 409
    response = domain.client.get(domain.path(f"leases/{domain.lease_id}"), headers=domain.headers)
    assert json_object(response)["status"] == "active"
    response = domain.client.get(
        domain.path(f"profiles/{domain.profile_id}"),
        headers=domain.headers,
    )
    assert json_object(response)["policy"] == POLICY
