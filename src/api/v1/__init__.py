"""API version 1 package.

.. prefix:: /api/v1

.. routes::
    - `/csrf`: Get a CSRF token.
    - `/auth`: Authenticate an internal user and return a Bearer token.
        - `/users/me/overview`: Get the authenticated user's identity and access resources.
    - `/users/me/password`: Change the authenticated user's internal password.

.. module_author:: Rémi Verschuur <rverschuur@audit-io.fr>
.. version:: 1.0.0
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import cast

from flask import Blueprint, Response, current_app, jsonify, request
from flask_wtf.csrf import CSRFProtect, generate_csrf
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

from api.common.db_objects.sessions import Session as UserSession
from api.common.other_objects import PasswordChange
from api.common.repositories import ConflictError, NotFoundError
from api.common.repositories import DeviceRepository, LeaseRepository, ProfileRepository
from api.common.repositories.leases import lease_status, utcnow
from auth.backends.internal import InternalAuthBackend
from auth.controller import AuthController
from auth.decorators import (
    get_authenticated_session_token,
    get_authenticated_user,
    require_authenticated_user,
)
from auth.exceptions import InvalidCredentialsError
from auth.manager import get_manager
from .admin import admin
from .user import user_api

api_v1 = Blueprint("api_v1", __name__, url_prefix="/api/v1")
api_v1.register_blueprint(admin)
api_v1.register_blueprint(user_api)



@api_v1.before_request
def protect_cookie_authenticated_requests() -> None:
    """Verify CSRF Token for API requests using cookies.

    :raises: 400 if the CSRF token is missing or invalid.
    """
    if request.method in {"GET", "HEAD", "OPTIONS", "TRACE"}:
        return

    scheme, separator, credentials = request.headers.get(
        "Authorization",
        "",
    ).partition(" ")

    if scheme.lower() == "bearer" and separator and credentials.strip():
        return

    csrf = cast(CSRFProtect, current_app.extensions["csrf"])
    csrf.protect(apply_exemptions=False)

@api_v1.get("/csrf")
def get_csrf_token():
    """Return a CSRF token.

    :returns: A JSON response containing the CSRF token.
    :rtype: Response
    """
    response = jsonify({"csrf_token": generate_csrf()})
    response.headers["Cache-Control"] = "no-store"
    return response

@api_v1.post("/auth")
def authenticate():
    """Authenticate an internal user and return a Bearer token.

    :returns: A JSON response containing the Bearer token.
    :rtype: Response
    """
    try:
        controller = AuthController(get_manager())
    except RuntimeError:
        return jsonify(error="Authentication manager not configured"), 501
    return controller.api_login(request.get_json(silent=True))


@api_v1.get("/users/me")
@require_authenticated_user
def get_current_user() -> Response:
    """Return the authenticated user's identity and active session expirations."""
    user = get_authenticated_user()
    database_session = current_app.extensions["database_config"].session()
    expirations = database_session.scalars(
        select(UserSession.expires_at).where(
            UserSession.user_id == user.id,
            UserSession.revoked_at.is_(None),
            UserSession.expires_at > utcnow(),
        ).order_by(UserSession.expires_at)
    )
    sessions: list[dict[str, str]] = []
    for expiration in expirations:
        normalized = (
            expiration.replace(tzinfo=timezone.utc)
            if expiration.tzinfo is None
            else expiration.astimezone(timezone.utc)
        )
        sessions.append({"expires_at": normalized.isoformat()})

    response = jsonify(
        user={
            "id": user.id,
            "username": user.username,
            "email": user.email,
            "is_admin": user.is_admin,
        },
        sessions=sessions,
    )
    response.headers["Cache-Control"] = "no-store"
    return response


def _format_timestamp(value: datetime | None) -> str | None:
    """Format a database timestamp as an ISO 8601 UTC value."""
    if value is None:
        return None
    normalized = (
        value.replace(tzinfo=timezone.utc)
        if value.tzinfo is None
        else value.astimezone(timezone.utc)
    )
    return normalized.isoformat()


@api_v1.get("/users/me/overview")
@require_authenticated_user
def get_current_user_overview() -> Response:
    """Return the authenticated user's identity and owned access resources."""
    user = get_authenticated_user()
    database_session = current_app.extensions["database_config"].session()
    user_id = str(user.id)

    devices = DeviceRepository(database_session).find(user=user_id)
    leases = LeaseRepository(database_session).find(user=user_id)
    profiles = ProfileRepository(database_session).find(user=user_id)

    device_rows: list[dict[str, object]] = [
        {
            "id": device.id,
            "name": device.name,
            "created_at": _format_timestamp(device.created_at),
            "revoked_at": _format_timestamp(device.revoked_at),
        }
        for device in devices
    ]
    lease_rows: list[dict[str, object]] = [
        {
            "id": lease.id,
            "device_id": lease.device_id,
            "profile_id": lease.profile_user.profile_id,
            "created_at": _format_timestamp(lease.created_at),
            "ended_at": _format_timestamp(lease.ended_at),
            "revoked_at": _format_timestamp(lease.revoked_at),
            "status": lease_status(lease),
        }
        for lease in leases
    ]
    profile_repository = ProfileRepository(database_session)
    profile_rows: list[dict[str, object]] = [
        {
            "id": profile.id,
            "name": profile.name,
            "policy": (
                policy.model_dump(mode="json")
                if (policy := profile_repository.policy(profile)) is not None
                else None
            ),
        }
        for profile in profiles
    ]

    response = jsonify(
        user={
            "id": user.id,
            "username": user.username,
            "email": user.email,
            "is_admin": user.is_admin,
        },
        devices=device_rows,
        leases=lease_rows,
        profiles=profile_rows,
    )
    response.headers["Cache-Control"] = "no-store"
    return response


@api_v1.post("/auth/logout")
@require_authenticated_user
def logout() -> Response:
    """Revoke the session used to authenticate this request."""
    get_manager().logout(get_authenticated_session_token())
    response = current_app.response_class(status=204)
    response.headers["Cache-Control"] = "no-store"
    if request.headers.get("Authorization") is None:
        cookie_name = cast(str, current_app.config["AUTH_COOKIE_NAME"])
        cookie_path = cast(str, current_app.config["SESSION_COOKIE_PATH"])
        response.delete_cookie(cookie_name, path=cookie_path)
    return response

def _update_password(data: PasswordChange) -> Response | tuple[Response, int]:
    """Delegate the password change and map service errors to HTTP responses.

    :param data: The password change request data.
    :type data: PasswordChange

    :returns: A response indicating the result of the password update.
    :rtype: Response or tuple[Response, int]
    """
    backend = get_manager().backend
    if not isinstance(backend, InternalAuthBackend):
        return jsonify(error="Internal password authentication is not enabled"), 409

    try:
        get_manager().user_service.change_password(
            get_authenticated_user().id,
            data.current_password,
            data.new_password,
            backend.password_hasher,
        )
    except NotFoundError:
        return jsonify(error="Authenticated user was not found"), 401
    except InvalidCredentialsError:
        return jsonify(error="Current password is incorrect"), 401
    except ConflictError:
        return jsonify(error="This account has no unique internal password credential"), 409
    except SQLAlchemyError:
        return jsonify(error="Unable to change password"), 500

    response = current_app.response_class(status=204)
    response.headers["Cache-Control"] = "no-store"
    return response


@api_v1.patch("/users/me/password")
@require_authenticated_user
def change_own_password() -> Response | tuple[Response, int]:
    """Validate the password-change request and update the authenticated account."""
    try:
        data = PasswordChange.model_validate(request.get_json(silent=True))
    except ValidationError as error:
        return jsonify(error="Invalid input", details=error.errors(
            include_input=False, include_context=False, include_url=False
        )), 400
    return _update_password(data)
