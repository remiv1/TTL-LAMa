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

import logging
from flask import Blueprint, Response, current_app, jsonify
from sqlalchemy.exc import SQLAlchemyError
from werkzeug.exceptions import HTTPException

from api.common.repositories import DeviceRepository, LeaseRepository
from api.logging_config import log_event
from auth.decorators import get_authenticated_user, require_authenticated_user
from .admin import (
    body,
    database_error,
    http_error,
    invalid_request,
    saved,
    serialize,
    get_session,
    wait_for_lease,
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
    repository = DeviceRepository(get_session())
    devices = repository.find(user=str(get_authenticated_user().id))
    return jsonify([serialize(device) for device in devices])


@user_api.get("/devices/<int:device_id>")
def get_device(device_id: int) -> Response:
    """Read an owned device without exposing another user's records."""
    device = DeviceRepository(get_session()).get_owned(
        device_id, str(get_authenticated_user().id)
    )
    return jsonify(serialize(device))


@user_api.post("/devices")
def add_device() -> tuple[Response, int]:
    """Create a device owned by the authenticated user."""
    data = body(DeviceCreate)
    device = DeviceRepository(get_session()).create(
        str(get_authenticated_user().id), data.name, data.public_key
    )
    return saved(device, 201)


@user_api.delete("/devices/<int:device_id>")
def delete_device(device_id: int) -> tuple[Response, int]:
    """Revoke an owned device and its active leases."""
    repository = DeviceRepository(get_session())
    device = repository.get_owned(device_id, str(get_authenticated_user().id))
    repository.block(device)
    get_session().commit()
    log_event(
        current_app.logger,
        logging.INFO,
        "device.revoke",
        "succeeded device_id=%s",
        device_id,
    )
    return Response(status=204), 204


@user_api.get("/leases")
def list_leases() -> Response:
    """List all leases owned by the authenticated user."""
    leases = LeaseRepository(get_session()).find(user=str(get_authenticated_user().id))
    return jsonify([serialize(lease) for lease in leases])


@user_api.get("/leases/<int:lease_id>")
def get_lease(lease_id: int) -> Response:
    """Read an owned lease without exposing another user's records."""
    lease = LeaseRepository(get_session()).get_owned(
        lease_id, str(get_authenticated_user().id)
    )
    return jsonify(serialize(lease))


@user_api.post("/leases")
def create_lease() -> tuple[Response, int]:
    """Create a lease subject to the user's device and profile policy."""
    user_id = str(get_authenticated_user().id)
    try:
        data = body(LeaseCreate)
        lease = LeaseRepository(get_session()).create(
            user_id=user_id,
            device_id=data.device_id,
            profile_id=data.profile_id,
            duration=data.duration,
        )
        get_session().commit()
    except (HTTPException, ValueError, SQLAlchemyError) as error:
        log_event(
            current_app.logger,
            logging.WARNING if isinstance(error, (HTTPException, ValueError)) else logging.ERROR,
            "lease.create",
            "failed error=%s",
            type(error).__name__,
        )
        raise
    log_event(
        current_app.logger,
        logging.INFO,
        "lease.create",
        "succeeded lease_id=%s user_id=%s device_id=%s profile_id=%s",
        lease.id,
        user_id,
        data.device_id,
        data.profile_id,
    )
    return wait_for_lease(lease.id, operation="apply")


@user_api.post("/leases/<int:lease_id>/revoke")
def revoke_lease(lease_id: int) -> tuple[Response, int]:
    """Revoke an owned lease without deleting its history."""
    try:
        repository = LeaseRepository(get_session())
        lease = repository.get_owned(lease_id, str(get_authenticated_user().id))
        repository.revoke(lease)
        get_session().commit()
    except (HTTPException, ValueError, SQLAlchemyError) as error:
        log_event(
            current_app.logger,
            logging.WARNING if isinstance(error, (HTTPException, ValueError)) else logging.ERROR,
            "lease.revoke",
            "failed error=%s",
            type(error).__name__,
        )
        raise
    log_event(
        current_app.logger,
        logging.INFO,
        "lease.revoke",
        "succeeded lease_id=%s",
        lease_id,
    )
    return wait_for_lease(lease.id, operation="delete")
