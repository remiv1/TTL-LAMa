"""Self-service API routes for the authenticated user's devices and leases.

.. prefix:: /users/me

.. routes::
    - `/devices`: GET List and POST create owned devices.
    - `/devices/<int:device_id>`: GET read and DELETE revoke an owned device.
    - `/leases`: GET list and POST create owned leases.
    - `/leases/<int:lease_id>`: GET read an owned lease.
    - `/leases/<int:lease_id>/revoke`: POST revoke an owned lease.

.. module_author:: Rémi Verschuur <rverschuur@audit-io.fr>
.. version:: 1.0.0
"""
from __future__ import annotations

from flask import Blueprint, Response, jsonify
from sqlalchemy.exc import SQLAlchemyError
from werkzeug.exceptions import HTTPException

from api.common.repositories import DeviceRepository, LeaseRepository
from auth.decorators import get_authenticated_user, require_authenticated_user
from .admin import (
    body,
    database_error,
    http_error,
    invalid_request,
    saved,
    serialize,
    session,
)
from .admin.schemas import DeviceCreate, LeaseCreate

user_api = Blueprint("user_api", __name__, url_prefix="/users/me")


@user_api.before_request
@require_authenticated_user
def authorize_user() -> None:
    """Require an enabled authenticated account for every self-service route."""


@user_api.after_request
def prevent_caching(response: Response) -> Response:
    """Prevent caching of user-owned resources."""
    response.headers["Cache-Control"] = "no-store"
    return response


user_api.register_error_handler(HTTPException, http_error)
user_api.register_error_handler(ValueError, invalid_request)
user_api.register_error_handler(SQLAlchemyError, database_error)


@user_api.get("/devices")
def list_devices() -> Response:
    """List all devices owned by the authenticated user."""
    repository = DeviceRepository(session())
    devices = repository.find(user=str(get_authenticated_user().id))
    return jsonify([serialize(device) for device in devices])


@user_api.get("/devices/<int:device_id>")
def get_device(device_id: int) -> Response:
    """Read an owned device without exposing another user's records."""
    device = DeviceRepository(session()).get_owned(
        device_id, str(get_authenticated_user().id)
    )
    return jsonify(serialize(device))


@user_api.post("/devices")
def add_device() -> tuple[Response, int]:
    """Create a device owned by the authenticated user."""
    data = body(DeviceCreate)
    device = DeviceRepository(session()).create(
        str(get_authenticated_user().id), data.name, data.public_key
    )
    return saved(device, 201)


@user_api.delete("/devices/<int:device_id>")
def delete_device(device_id: int) -> tuple[Response, int]:
    """Revoke an owned device and its active leases."""
    repository = DeviceRepository(session())
    device = repository.get_owned(device_id, str(get_authenticated_user().id))
    repository.block(device)
    session().commit()
    return Response(status=204), 204


@user_api.get("/leases")
def list_leases() -> Response:
    """List all leases owned by the authenticated user."""
    leases = LeaseRepository(session()).find(user=str(get_authenticated_user().id))
    return jsonify([serialize(lease) for lease in leases])


@user_api.get("/leases/<int:lease_id>")
def get_lease(lease_id: int) -> Response:
    """Read an owned lease without exposing another user's records."""
    lease = LeaseRepository(session()).get_owned(
        lease_id, str(get_authenticated_user().id)
    )
    return jsonify(serialize(lease))


@user_api.post("/leases")
def create_lease() -> tuple[Response, int]:
    """Create a lease subject to the user's device and profile policy."""
    data = body(LeaseCreate)
    lease = LeaseRepository(session()).create(
        user_id=str(get_authenticated_user().id),
        device_id=data.device_id,
        profile_id=data.profile_id,
        duration=data.duration,
    )
    return saved(lease, 201)


@user_api.post("/leases/<int:lease_id>/revoke")
def revoke_lease(lease_id: int) -> tuple[Response, int]:
    """Revoke an owned lease without deleting its history."""
    repository = LeaseRepository(session())
    lease = repository.get_owned(lease_id, str(get_authenticated_user().id))
    return saved(repository.revoke(lease))
