"""API version 1 package.

.. prefix:: /api/v1

.. routes::
    - `/csrf`: Get a CSRF token.
    - `/auth`: Authenticate an internal user and return a Bearer token.
    - `/global-config`: Read the application YAML configuration.
    - `/global-config/validate`: Validate an application YAML candidate.
    - `/global-config/apply`: Persist an application YAML candidate.
        - `/users/me/overview`: Get the authenticated user's identity and access resources.
    - `/users/me/password`: Change the authenticated user's internal password.

.. module_author:: Rémi Verschuur <rverschuur@audit-io.fr>
.. version:: 1.0.0
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import cast

from flask import Blueprint, Response, current_app, jsonify, request
from flask_wtf.csrf import CSRFProtect, generate_csrf
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from werkzeug.exceptions import HTTPException
from requests.exceptions import RequestException

from api.database import get_session
from api.logging_config import log_event
from api.common.db_objects import User
from api.common.db_objects.sessions import Session as UserSession
from api.common.other_objects import PasswordChange
from api.common.repositories import ConflictError, NotFoundError
from api.common.repositories import DeviceRepository, LeaseRepository, ProfileRepository
from api.common.repositories.leases import lease_status, utcnow
from api.config.global_config import (
    GlobalConfigError,
    configuration_path,
    is_volume_mounted,
    load_configuration,
    redact_secrets,
    unchanged_secret_paths,
    validate_configuration,
    write_configuration,
)
from auth.backends.internal import InternalAuthBackend
from auth.controller import AuthController
from auth.decorators import (
    get_authenticated_session_token,
    get_authenticated_user,
    require_admin,
    require_authenticated_user,
)
from auth.exceptions import InvalidCredentialsError, OIDCAuthenticationError
from auth.manager import get_manager
from auth.models import UnifiedUser
from auth.services.cli_login_ticket import (
    CLI_LOGIN_TICKET_LIFETIME,
    CliLoginTicketService,
)
from .admin import admin
from .user import user_api

global_config = Blueprint(
    "global_config",
    __name__,
    url_prefix="/global-config",
)
_OIDC_DEVICE_START_OPERATION = "auth.oidc.device.start"
_OIDC_DEVICE_POLL_OPERATION = "auth.oidc.device.poll"


@global_config.before_request
@require_admin
def authorize_global_config() -> None:
    """Require the same persisted administrator authorization as admin routes."""


@global_config.after_request
def prevent_global_config_caching(response: Response) -> Response:
    """Prevent caching configuration responses that may contain redacted secrets."""
    response.headers["Cache-Control"] = "no-store"
    return response


@global_config.errorhandler(HTTPException)
def global_config_http_error(error: HTTPException) -> tuple[Response, int]:
    """Keep authorization and request errors in the administrative JSON format."""
    return jsonify(error=error.description), error.code or 500


@global_config.get("")
def get_global_config() -> Response | tuple[Response, int]:
    """Read the current YAML configuration with direct secrets masked."""
    try:
        return jsonify(redact_secrets(load_configuration()))
    except GlobalConfigError as error:
        log_event(
            current_app.logger,
            logging.ERROR,
            "config.read",
            "configuration read failed error=%s",
            type(error).__name__,
        )
        return jsonify(error="Unable to read the application configuration."), 500


@global_config.post("/validate")
def validate_global_config() -> Response:
    """Validate an application YAML candidate without persisting it."""
    errors = validate_configuration(request.get_json(silent=True))
    return jsonify(valid=not errors, errors=errors)


@global_config.post("/compare")
def compare_global_config() -> tuple[Response, int] | Response:
    """Compare direct candidate secrets without returning their values."""
    candidate = request.get_json(silent=True)
    errors = validate_configuration(candidate)
    if errors:
        return jsonify(error="Invalid configuration", details=errors), 400

    try:
        unchanged = unchanged_secret_paths(candidate)
    except GlobalConfigError as error:
        log_event(
            current_app.logger,
            logging.ERROR,
            "config.compare",
            "secret comparison failed error=%s",
            type(error).__name__,
        )
        return jsonify(error="Unable to compare application secrets."), 500
    return jsonify(unchanged_secrets=unchanged)


@global_config.post("/apply")
def apply_global_config() -> tuple[Response, int] | Response:
    """Validate and atomically persist an application YAML candidate."""
    candidate = request.get_json(silent=True)
    errors = validate_configuration(candidate)
    if errors:
        return jsonify(error="Invalid configuration", details=errors), 400

    try:
        write_configuration(cast(dict[str, object], candidate))
    except GlobalConfigError as error:
        log_event(
            current_app.logger,
            logging.ERROR,
            "config.write",
            "configuration write failed error=%s",
            type(error).__name__,
        )
        return jsonify(error="Unable to write the application configuration."), 500

    mounted = is_volume_mounted(configuration_path())
    return jsonify(
        applied=True,
        restart_required=True,
        warning=None if mounted else (
            "The configuration file is not covered by a volume mount; "
            "the change may be lost when the container is replaced."
        ),
    )


api_v1 = Blueprint("api_v1", __name__, url_prefix="/api/v1")
_INVALID_CLI_LOGIN_TICKET = "Invalid or expired login ticket"
api_v1.register_blueprint(admin)
api_v1.register_blueprint(user_api)
api_v1.register_blueprint(global_config)



@api_v1.before_request
def protect_cookie_authenticated_requests() -> None:
    """Verify CSRF Token for API requests using cookies.

    :raises: 400 if the CSRF token is missing or invalid.
    """
    if request.method in {"GET", "HEAD", "OPTIONS", "TRACE"}:
        return

    if request.endpoint in {
        "api_v1.exchange_oidc_cli_ticket",
        "api_v1.begin_oidc_device_authorization",
        "api_v1.poll_oidc_device_authorization",
    }:
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


def _no_store(response: Response) -> Response:
    """Prevent caching authentication flow responses."""
    response.headers["Cache-Control"] = "no-store"
    return response


@api_v1.post("/auth/oidc/exchange")
def exchange_oidc_cli_ticket() -> tuple[Response, int] | Response:
    """Exchange a short-lived CLI login ticket for a Bearer session."""
    raw_payload = request.get_json(silent=True)
    payload = cast(dict[str, object], raw_payload) if isinstance(raw_payload, dict) else {}
    ticket = payload.get("ticket")
    if not isinstance(ticket, str) or not ticket:
        return _no_store(jsonify(error=_INVALID_CLI_LOGIN_TICKET)), 400

    ticket_service = CliLoginTicketService(
        get_session(),
        CLI_LOGIN_TICKET_LIFETIME,
    )
    user_id = ticket_service.consume(ticket)
    if user_id is None:
        return _no_store(jsonify(error=_INVALID_CLI_LOGIN_TICKET)), 401

    database_session = get_session()
    user = database_session.get(User, user_id)
    if user is None or not user.enabled:
        return _no_store(jsonify(error=_INVALID_CLI_LOGIN_TICKET)), 401

    result = get_manager().create_session(UnifiedUser.from_db_user(user))
    return _no_store(jsonify(
        access_token=result.session_token,
        token_type="Bearer",
    ))


@api_v1.post("/auth/oidc/device")
def begin_oidc_device_authorization() -> tuple[Response, int] | Response:
    """Start a Device Authorization request with the configured OIDC provider."""
    app_config = cast(dict[str, object], current_app.config)
    if app_config.get("AUTH_MODE") != "external":
        return _no_store(jsonify(error="OIDC authentication is not enabled")), 501

    try:
        response_data = get_manager().backend.begin_device_authorization(
            cast(str, app_config["OIDC_CLIENT_ID"]),
            cast(str, app_config["OIDC_CLIENT_SECRET"]),
        )
    except RuntimeError as error:
        log_event(
            current_app.logger,
            logging.WARNING,
            _OIDC_DEVICE_START_OPERATION,
            "unavailable error=%s",
            type(error).__name__,
        )
        return _no_store(jsonify(error="OIDC device authorization is unavailable")), 501
    except (OIDCAuthenticationError, RequestException, ValueError, KeyError) as error:
        log_event(
            current_app.logger,
            logging.ERROR,
            _OIDC_DEVICE_START_OPERATION,
            "authorization request failed error=%s",
            type(error).__name__,
        )
        return _no_store(jsonify(error="Unable to start OIDC device authorization")), 502

    return _no_store(jsonify(response_data))


@api_v1.post("/auth/oidc/device/poll")
def poll_oidc_device_authorization() -> tuple[Response, int] | Response:
    """Poll a Device Authorization request and create a local session on success."""
    app_config = cast(dict[str, object], current_app.config)
    if app_config.get("AUTH_MODE") != "external":
        return _no_store(jsonify(error="OIDC authentication is not enabled")), 501
    raw_payload = request.get_json(silent=True)
    payload = cast(dict[str, object], raw_payload) if isinstance(raw_payload, dict) else {}
    device_code = payload.get("device_code")
    if not isinstance(device_code, str) or not device_code:
        return _no_store(jsonify(error="Invalid device authorization code")), 400

    try:
        result = get_manager().backend.poll_device_authorization(
            device_code,
            cast(str, app_config["OIDC_CLIENT_ID"]),
            cast(str, app_config["OIDC_CLIENT_SECRET"]),
        )
    except RuntimeError as error:
        log_event(
            current_app.logger,
            logging.WARNING,
            _OIDC_DEVICE_POLL_OPERATION,
            "unavailable error=%s",
            type(error).__name__,
        )
        return _no_store(jsonify(error="OIDC device authorization is unavailable")), 501
    except (OIDCAuthenticationError, RequestException, ValueError, KeyError) as error:
        log_event(
            current_app.logger,
            logging.ERROR,
            _OIDC_DEVICE_POLL_OPERATION,
            "authorization poll failed error=%s",
            type(error).__name__,
        )
        return _no_store(jsonify(error="Unable to poll OIDC device authorization")), 502

    if result.get("status") != "complete":
        return _no_store(jsonify(status=result.get("status")))
    user = result.get("user")
    if not isinstance(user, UnifiedUser):
        return _no_store(jsonify(error="OIDC provider returned an invalid identity")), 502

    authentication = get_manager().create_session(user)
    log_event(
        current_app.logger,
        logging.INFO,
        _OIDC_DEVICE_POLL_OPERATION,
        "succeeded",
    )
    return _no_store(jsonify(
        status="complete",
        access_token=authentication.session_token,
        token_type="Bearer",
    ))


@api_v1.get("/users/me")
@require_authenticated_user
def get_current_user() -> Response:
    """Return the authenticated user's identity and active session expirations."""
    user = get_authenticated_user()
    database_session = get_session()
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
    database_session = get_session()
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
