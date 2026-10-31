"""API version 1 package.

.. prefix:: /api/v1

.. routes::
    - TODO

.. module_author:: Rémi Verschuur <rverschuur@audit-io.fr>
.. version:: 1.0.0
"""
from __future__ import annotations

from typing import cast, Annotated

from argon2.exceptions import InvalidHashError, VerificationError
from flask import Blueprint, Response, current_app, jsonify, request
from flask_wtf.csrf import CSRFProtect, generate_csrf
from pydantic import BaseModel, ConfigDict, StringConstraints, ValidationError
from sqlalchemy.exc import SQLAlchemyError

from api.common.other_objects import AuthMethod
from api.common.repositories import NotFoundError, UserRepository
from auth.backends.internal import InternalAuthBackend
from auth.controller import AuthController
from auth.decorators import get_authenticated_user, require_authenticated_user
from auth.manager import get_manager
from .admin import admin

api_v1 = Blueprint("api_v1", __name__, url_prefix="/api/v1")
api_v1.register_blueprint(admin)

Password = Annotated[str, StringConstraints(min_length=1, max_length=1024)]


class PasswordChange(BaseModel):
    """Strict request body for self-service password changes."""

    model_config = ConfigDict(extra="forbid", strict=True)

    current_password: Password
    new_password: Password


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

@api_v1.patch("/users/me/password")
@require_authenticated_user
def change_own_password() -> Response | tuple[Response, int]:
    """Change the authenticated user's internal password and revoke all sessions.
    TODO: Alléger la route"""
    try:
        data = PasswordChange.model_validate(request.get_json(silent=True))
    except ValidationError as error:
        return jsonify(error="Invalid input", details=error.errors(
            include_input=False, include_context=False, include_url=False
        )), 400

    backend = get_manager().backend
    if not isinstance(backend, InternalAuthBackend):
        return jsonify(error="Internal password authentication is not enabled"), 409

    database_session = current_app.extensions["database_config"].session()
    repository = UserRepository(database_session)
    try:
        user = repository.get(get_authenticated_user().id)
    except NotFoundError:
        database_session.rollback()
        return jsonify(error="Authenticated user was not found"), 401
    credentials = [
        credential for credential in user.credentials
        if credential.auth_method == AuthMethod.INTERNAL.value
    ]
    if len(credentials) != 1:
        return jsonify(error="This account has no unique internal password credential"), 409

    try:
        backend.password_hasher.verify(credentials[0].hash_password, data.current_password)
    except (VerificationError, InvalidHashError):
        database_session.rollback()
        return jsonify(error="Current password is incorrect"), 401

    try:
        repository.set_password(user, backend.password_hasher.hash(data.new_password))
        database_session.commit()
    except SQLAlchemyError:
        database_session.rollback()
        return jsonify(error="Unable to change password"), 500

    response = current_app.response_class(status=204)
    response.headers["Cache-Control"] = "no-store"
    return response
