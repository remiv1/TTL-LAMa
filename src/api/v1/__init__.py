"""API version 1 package.

.. module_author:: Rémi Verschuur <rverschuur@audit-io.fr>
.. version:: 1.0.0
"""
from __future__ import annotations

from typing import cast

from flask import Blueprint, current_app, jsonify, request
from flask_wtf.csrf import CSRFProtect, generate_csrf

from auth.manager import AuthManager

api_v1 = Blueprint("api_v1", __name__, url_prefix="/api/v1")

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
    app_config = cast(dict[str, object], current_app.config)
    if app_config.get("AUTH_MODE") != "internal":
        return jsonify(error="Authentication mode not supported"), 405

    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify(error="Invalid payload. Expected a JSON object."), 400

    manager = cast(AuthManager, current_app.extensions["auth_manager"])
    result = manager.authenticate(cast(dict[str, object], payload))
    if result is None:
        return jsonify(error="Invalid username or password"), 401

    response = jsonify(
        user={
            "id": result.user.id,
            "username": result.user.username,
            "email": result.user.email,
            "is_admin": result.user.is_admin
        },
        access_token=result.session_token,
        token_type="Bearer",
    )
    response.headers["Cache-Control"] = "no-store"
    return response
