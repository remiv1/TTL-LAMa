"""Authentication routes for the Flask application.

.. prefix:: /auth

.. routes::
    - `/login`:
        - `GET`: Render the login page.

.. module_author:: Rémi Verschuur <rverschuur@audit-io.fr>
.. version:: 1.0.0
"""
from __future__ import annotations

from typing import cast

from flask import Blueprint, Response, current_app, abort, redirect, jsonify, request
from werkzeug import Response as WerkzeugResponse

from auth.manager import AuthManager

auth_bp = Blueprint("auth", __name__, url_prefix="/auth")

@auth_bp.get("/login")
def login() -> Response:
    """Render the appropriate login page."""
    auth_manager = cast(
        AuthManager | None,
        current_app.extensions.get("auth_manager"),
    )
    if auth_manager is None:
        abort(501, description="Authentication manager not configured.")

    response = auth_manager.begin_login()

    if response is None:
        abort(501, description="OIDC client not configured.")

    return response

@auth_bp.get("/callback")
def call_back() -> WerkzeugResponse:
    """Handle the callback from the OIDC provider."""
    auth_manager = cast(AuthManager, current_app.extensions["auth_manager"])
    result = auth_manager.complete_login()
    app_config = cast(dict[str, object], current_app.config)
    configured_target = app_config.get("AUTH_SUCCESS_REDIRECT") or "/"

    target = cast(str, configured_target)
    response = redirect(target)
    response.set_cookie(
        key=cast(str, current_app.config["AUTH_COOKIE_NAME"]),
        value=result.session_token,
        max_age=cast(int, current_app.config["SESSION_LIFETIME"]),
        httponly=cast(bool, current_app.config["SESSION_COOKIE_HTTPONLY"]),
        secure=cast(bool, current_app.config["SESSION_COOKIE_SECURE"]),
        samesite=cast(str, current_app.config["SESSION_COOKIE_SAMESITE"]),
        path=cast(str, current_app.config["SESSION_COOKIE_PATH"]),
    )
    response.headers["Cache-Control"] = "no-store"
    return response

@auth_bp.post("/login")
def internal_login() -> Response | tuple[Response, int]:
    """Authenticate internal credentials and set the session cookie."""
    app_config = cast(dict[str, object], current_app.config)
    if app_config.get("AUTH_MODE") != "internal":
        return jsonify(error="Credential authentication is not enabled"), 405

    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify(error="A JSON object is required"), 400

    manager = cast(AuthManager, current_app.extensions["auth_manager"])
    result = manager.authenticate(cast(dict[str, object], payload))
    if result is None:
        return jsonify(error="Invalid username or password"), 401

    response = jsonify(
        user={
            "id": result.user.id,
            "username": result.user.username,
            "email": result.user.email,
            "is_admin": result.user.is_admin,
        },
    )
    response.set_cookie(
        key=cast(str, app_config["AUTH_COOKIE_NAME"]),
        value=result.session_token,
        max_age=cast(int, app_config["SESSION_LIFETIME"]),
        httponly=cast(bool, app_config["SESSION_COOKIE_HTTPONLY"]),
        secure=cast(bool, app_config["SESSION_COOKIE_SECURE"]),
        samesite=cast(str, app_config["SESSION_COOKIE_SAMESITE"]),
        path=cast(str, app_config["SESSION_COOKIE_PATH"]),
    )
    response.headers["Cache-Control"] = "no-store"
    return response
