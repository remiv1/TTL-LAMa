"""API version 1 package.

.. module_author:: Rémi Verschuur <rverschuur@audit-io.fr>
.. version:: 1.0.0
"""
from __future__ import annotations

from typing import cast

from flask import Blueprint, current_app, jsonify, request
from flask_wtf.csrf import CSRFProtect, generate_csrf

from auth.controller import AuthController
from auth.manager import get_manager
from .admin import admin

api_v1 = Blueprint("api_v1", __name__, url_prefix="/api/v1")
api_v1.register_blueprint(admin)

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
