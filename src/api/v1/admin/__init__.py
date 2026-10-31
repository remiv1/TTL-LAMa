"""Administrative HTTP adapter over transaction-neutral repositories.

.. functions::
    - `session`: Obtain the current request-scoped database session.
    - `body`: Validate and parse the request body against a Pydantic schema.
    - `filters`: Validate and parse query parameters against a Pydantic schema.
    - `serialize`: Convert a database model instance to a JSON-serializable dictionary.
    - `saved`: Commit the current session and return a serialized response.
    - `hash_password`: Hash a password using the internal authentication backend.
    - `http_error`: Return consistent JSON errors for HTTP exceptions.
    - `invalid_request`: Return consistent JSON errors for invalid request data.
    - `database_error`: Return consistent JSON errors for database failures.

.. prefix:: /admin

.. routes::
    - `/users`: GET Lists users.
    - `/users/<uuid:user_id>`: GET Retrieve a specific user by ID.
    - `/users`: POST Create a new user.
    - `/users/<uuid:user_id>`: PATCH Update a specific user by ID and invalidate sessions.
    - `/users/<uuid:user_id>`: DELETE Logically delete a specific user by ID and invalidate
    sessions.
    - `/users/<uuid:user_id>/profiles`: GET List profiles for a specific user by ID.
    - `/users/<uuid:user_id>/profiles/<uuid:profile_id>`: PUT Assign a specific profile for a
    specific user by ID.
    - `/users/<uuid:user_id>/profiles/<uuid:profile_id>`: DELETE Unassign a specific profile and its
    leases for a specific user by ID.
    - `/devices`: Lists devices.
    - `/devices/<int:device_id>`: GET Retrieve a specific device by ID.
    - `/devices/<int:device_id>`: PATCH Update a specific device by ID.
    - `/devices/<int:device_id>/block`: POST Block a specific device by ID.
    - `/devices/<int:device_id>`: DELETE Delete a specific device by ID.
    - `/leases`: Lists leases.
    - `/leases/<int:lease_id>`: GET Retrieve a specific lease by ID.
    - `/leases/<int:lease_id>/revoke`: POST Revoke a specific lease by ID.
    - `/profiles`: Lists profiles.
    - `/profiles/<int:profile_id>`: GET Retrieve a specific profile by ID.
    - `/profiles`: POST Create a new profile.
    - `/profiles/<int:profile_id>`: PATCH Update a specific profile by ID.
    - `/profiles/<int:profile_id>`: DELETE Delete a specific profile by ID.

.. module_author:: Rémi Verschuur <rverschuur@audit-io.fr>
.. version:: 1.0.0
"""
from __future__ import annotations

import secrets
from datetime import datetime, timezone
from typing import TypeVar
from uuid import UUID

from flask import Blueprint, Response, current_app, jsonify, request
from pydantic import BaseModel, ValidationError
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session
from werkzeug.exceptions import HTTPException

from api.common.db_objects._common import Base
from api.common.db_objects.leases import Lease
from api.common.db_objects.profiles import Profile
from api.common.repositories import (
    ConflictError, DeviceRepository, LeaseRepository, NotFoundError,
    ProfileRepository, UserRepository,
)
from api.common.repositories.leases import lease_status
from api.config.c_profiles import AccessProfile
from auth.backends.internal import InternalAuthBackend
from auth.decorators import require_admin
from auth.manager import get_manager
from .schemas import (
    DeviceFilters, DevicePatch, LeaseFilters, ProfileCreate, ProfileFilters,
    ProfilePatch, UserCreate, UserFilters, UserPatch,
)

admin = Blueprint("admin", __name__, url_prefix="/admin")
Schema = TypeVar("Schema", bound=BaseModel)


@admin.before_request
@require_admin
def authorize_admin() -> None:
    """Protect every admin endpoint, including newly registered routes. Function is applied before
    every request to ensure the user has administrative privileges.
    """


@admin.after_request
def prevent_caching(response: Response) -> Response:
    """Do not cache administrative data.
    
    :param response: The HTTP response object to modify.
    :type response: Response
    :return: The modified HTTP response object.
    :rtype: Response
    """
    response.headers["Cache-Control"] = "no-store"
    return response


def session() -> Session:
    """Obtain the current request-scoped database session.
    
    :return: The current request-scoped database session.
    :rtype: Session
    """
    return current_app.extensions["database_config"].session()


def body(schema: type[Schema]) -> Schema:
    """Validate an object body and reject empty patches and explicit nulls.
    
    :param schema: The Pydantic schema class to validate against.
    :type schema: type[Schema]
    :return: The validated and parsed object.
    :rtype: Schema
    """
    data: object = request.get_json()
    parsed = schema.model_validate(data)
    if not parsed.model_fields_set:
        raise ValueError("At least one field is required")
    for field in parsed.model_fields_set - {"email"}:
        if getattr(parsed, field) is None:
            raise ValueError(f"{field} cannot be null")
    return parsed


def filters(schema: type[Schema]) -> Schema:
    """Reject duplicate filters rather than silently selecting one.
    
    :param schema: The Pydantic schema class to validate against.
    :type schema: type[Schema]
    :return: The validated and parsed filters.
    :rtype: Schema
    """
    if any(len(request.args.getlist(key)) != 1 for key in request.args):
        raise ValueError("Filters must not be repeated")
    return schema.model_validate(request.args.to_dict())


def serialize(instance: Base) -> dict[str, object]:
    """Expose scalar domain columns only, never relationships or credentials.
    
    :param instance: The domain model instance to serialize.
    :type instance: Base
    :return: A dictionary representation of the instance with scalar columns.
    :rtype: dict[str, object]
    """
    result: dict[str, object] = {}
    for column in instance.__table__.columns:
        value: object = getattr(instance, column.name)
        if isinstance(value, datetime):
            value = value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value
            value = value.isoformat()
        result[column.name] = value
    if isinstance(instance, Lease):
        result["status"] = lease_status(instance)
        result["profile_id"] = instance.profile_user.profile_id
    if isinstance(instance, Profile):
        policy = ProfileRepository(session()).policy(instance)
        result["policy"] = policy.model_dump(mode="json") if policy else None
    return result


def saved(instance: Base, status: int = 200) -> tuple[Response, int]:
    """Commit a complete domain operation before reporting success.
    
    :param instance: The domain model instance that was saved.
    :type instance: Base
    :param status: The HTTP status code to return, defaults to 200.
    :type status: int, optional
    :return: A tuple containing the JSON response and the HTTP status code.
    :rtype: tuple[Response, int]
    """
    session().commit()
    return jsonify(serialize(instance)), status


def hash_password(password: str) -> str:
    """Reuse the configured internal authentication hasher.
    
    :param password: The plaintext password to hash.
    :type password: str
    :return: The hashed password.
    :rtype: str
    """
    backend = get_manager().backend
    if not isinstance(backend, InternalAuthBackend):
        raise ValueError("Passwords can only be managed in internal authentication mode")
    return backend.password_hasher.hash(password)


@admin.errorhandler(HTTPException)
def http_error(error: HTTPException) -> tuple[Response, int]:
    """Return consistent JSON errors for authentication and request failures.
    
    :param error: The HTTP exception that occurred.
    :type error: HTTPException
    :return: A tuple containing the JSON response and the HTTP status code.
    :rtype: tuple[Response, int]
    """
    return jsonify(error=error.description), error.code or 500


@admin.errorhandler(ValueError)
def invalid_request(error: ValueError) -> tuple[Response, int]:
    """Report input errors without echoing passwords or database details.
    
    :param error: The ValueError that occurred.
    :type error: ValueError
    :return: A tuple containing the JSON response and the HTTP status code.
    :rtype: tuple[Response, int]
    """
    session().rollback()
    if isinstance(error, ValidationError):
        return jsonify(error="Invalid input", details=error.errors(
            include_input=False, include_context=False, include_url=False
        )), 400
    if isinstance(error, NotFoundError):
        return jsonify(error=str(error)), 404
    if isinstance(error, ConflictError):
        return jsonify(error=str(error)), 409
    return jsonify(error=str(error)), 400


@admin.errorhandler(SQLAlchemyError)
def database_error(error: SQLAlchemyError) -> tuple[Response, int]:
    """Roll back failed operations and keep database internals private.
    
    :param error: The SQLAlchemy error that occurred.
    :type error: SQLAlchemyError
    :return: A tuple containing the JSON response and the HTTP status code.
    :rtype: tuple[Response, int]
    """
    session().rollback()
    if isinstance(error, IntegrityError):
        return jsonify(error="Operation conflicts with existing data"), 409
    current_app.logger.error("Admin database operation failed: %s", type(error).__name__)
    return jsonify(error="Database operation failed"), 500


@admin.get("/users")
def list_users() -> Response:
    """List users with combined relationship filters."""
    query = filters(UserFilters)
    users = UserRepository(session()).find(
        device=query.device, lease=query.lease, profile=query.profile
    )
    return jsonify([serialize(user) for user in users])


@admin.get("/users/<uuid:user_id>")
def get_user(user_id: UUID) -> Response:
    """Read a user without exposing authentication data."""
    return jsonify(serialize(UserRepository(session()).get(str(user_id))))


@admin.post("/users")
def create_user() -> tuple[Response, int]:
    """Create a user and optional internal credentials atomically."""
    data = body(UserCreate)
    password = data.password
    generated_password: str | None = None
    if password is None and isinstance(get_manager().backend, InternalAuthBackend):
        generated_password = secrets.token_urlsafe(32)
        password = generated_password

    user = UserRepository(session()).create(
        username=data.username, email=data.email,
        enabled=data.enabled, is_admin=data.is_admin,
        password_hash=hash_password(password) if password is not None else None,
    )
    if generated_password is not None:
        session().commit()
        return jsonify(
            user=serialize(user),
            generated_password=generated_password,
        ), 201
    return saved(user, 201)


@admin.patch("/users/<uuid:user_id>")
def update_user(user_id: UUID) -> tuple[Response, int]:
    """Update an identity, invalidating sessions after sensitive changes."""
    data = body(UserPatch)
    repository = UserRepository(session())
    user = repository.get(str(user_id))
    if data.username is not None:
        user.username = data.username
    if "email" in data.model_fields_set:
        user.email = data.email
    if data.is_admin is not None:
        repository.set_admin(user, data.is_admin)
    if data.password is not None:
        repository.set_password(user, hash_password(data.password))
    if data.enabled is False:
        repository.disable(user)
    elif data.enabled is True:
        user.enabled = True
    return saved(user)


@admin.delete("/users/<uuid:user_id>")
def delete_user(user_id: UUID) -> tuple[Response, int]:
    """Logically delete an identity and its dependent access."""
    repository = UserRepository(session())
    repository.disable(repository.get(str(user_id)))
    session().commit()
    return Response(status=204), 204


@admin.get("/users/<uuid:user_id>/profiles")
def list_user_profiles(user_id: UUID) -> Response:
    """Read active profile assignments for an existing user."""
    UserRepository(session()).get(str(user_id))
    return jsonify(
        [serialize(profile) for profile in
        ProfileRepository(session()).find(user=str(user_id))]
    )


@admin.put("/users/<uuid:user_id>/profiles/<int:profile_id>")
def assign_profile(user_id: UUID, profile_id: int) -> tuple[Response, int]:
    """Assign a profile idempotently."""
    repository = ProfileRepository(session())
    assignment = repository.assign(
        UserRepository(session()).get(str(user_id)), repository.get(profile_id)
    )
    return saved(assignment)


@admin.delete("/users/<uuid:user_id>/profiles/<int:profile_id>")
def unassign_profile(user_id: UUID, profile_id: int) -> tuple[Response, int]:
    """Revoke an assignment and its leases."""
    repository = ProfileRepository(session())
    repository.unassign(
        UserRepository(session()).get(str(user_id)), repository.get(profile_id)
    )
    session().commit()
    return Response(status=204), 204


@admin.get("/devices")
def list_devices() -> Response:
    """List devices through optional lease and profile filters."""
    query = filters(DeviceFilters)
    return jsonify([serialize(device) for device in DeviceRepository(session()).find(
        lease=query.lease, profile=query.profile
    )])


@admin.get("/devices/<int:device_id>")
def get_device(device_id: int) -> Response:
    """Read a device."""
    return jsonify(serialize(DeviceRepository(session()).get(device_id)))


@admin.patch("/devices/<int:device_id>")
def update_device(device_id: int) -> tuple[Response, int]:
    """Update supported device metadata."""
    data = body(DevicePatch)
    repository = DeviceRepository(session())
    return saved(repository.update(
        repository.get(device_id), name=data.name, public_key=data.public_key
    ))


@admin.post("/devices/<int:device_id>/block")
def block_device(device_id: int) -> tuple[Response, int]:
    """Block a device and revoke its leases."""
    repository = DeviceRepository(session())
    return saved(repository.block(repository.get(device_id)))


@admin.delete("/devices/<int:device_id>")
def delete_device(device_id: int) -> tuple[Response, int]:
    """Logically delete a device using its revocation state."""
    repository = DeviceRepository(session())
    repository.block(repository.get(device_id))
    session().commit()
    return Response(status=204), 204


@admin.get("/leases")
def list_leases() -> Response:
    """List leases using combined filters and derived lifecycle status."""
    query = filters(LeaseFilters)
    return jsonify([serialize(lease) for lease in LeaseRepository(session()).find(
        user=str(query.user) if query.user else None, device=query.device,
        profile=query.profile, status=query.status,
    )])


@admin.get("/leases/<int:lease_id>")
def get_lease(lease_id: int) -> Response:
    """Read a lease."""
    return jsonify(serialize(LeaseRepository(session()).get(lease_id)))


@admin.post("/leases/<int:lease_id>/revoke")
def revoke_lease(lease_id: int) -> tuple[Response, int]:
    """Revoke a lease without deleting history."""
    repository = LeaseRepository(session())
    return saved(repository.revoke(repository.get(lease_id)))


@admin.get("/profiles")
def list_profiles() -> Response:
    """List persisted profile policies."""
    query = filters(ProfileFilters)
    return jsonify([serialize(profile) for profile in ProfileRepository(session()).find(
        user=str(query.user) if query.user else None, device=query.device, lease=query.lease
    )])


@admin.get("/profiles/<int:profile_id>")
def get_profile(profile_id: int) -> Response:
    """Read a profile and its policy."""
    return jsonify(serialize(ProfileRepository(session()).get(profile_id)))


@admin.post("/profiles")
def create_profile() -> tuple[Response, int]:
    """Create a profile with a validated duration and network policy."""
    data = body(ProfileCreate)
    policy = AccessProfile.model_validate(data.model_dump(exclude={"name"}))
    return saved(ProfileRepository(session()).create(data.name, policy), 201)


@admin.patch("/profiles/<int:profile_id>")
def update_profile(profile_id: int) -> tuple[Response, int]:
    """Validate the complete merged policy before staging any changes."""
    data = body(ProfilePatch)
    repository = ProfileRepository(session())
    profile = repository.get(profile_id)
    if profile.revoked_at is not None:
        raise ConflictError("Cannot update a revoked profile")
    policy_fields = data.model_fields_set - {"name"}
    if policy_fields:
        current = repository.policy(profile)
        merged = current.model_dump(mode="json") if current else {}
        merged.update(data.model_dump(include=policy_fields))
        repository.set_policy(profile, AccessProfile.model_validate(merged))
    if data.name is not None:
        repository.ensure_name(data.name, profile.id)
        profile.name = data.name
    return saved(profile)


@admin.delete("/profiles/<int:profile_id>")
def delete_profile(profile_id: int) -> tuple[Response, int]:
    """Revoke the profile and all dependent access."""
    repository = ProfileRepository(session())
    repository.delete(repository.get(profile_id))
    session().commit()
    return Response(status=204), 204
