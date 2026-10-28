"""Authentication routes for the Flask application.

.. prefix:: /auth

.. routes::
    - `/login`:
        - `GET`: Render the login page.
        - `POST`: Authenticate internal credentials and set the session cookie.
    - `/callback`:
        - `GET`: Handle the callback from the OIDC provider.

.. module_author:: Rémi Verschuur <rverschuur@audit-io.fr>
.. version:: 1.0.0
"""
from __future__ import annotations

from flask import Blueprint, Response,  abort,  request
from werkzeug import Response as WerkzeugResponse

from auth.controller import AuthController
from auth.manager import get_manager

_NON_MANAGED_ERROR = "Authentication manager not configured."

auth_bp = Blueprint("auth", __name__, url_prefix="/auth")

@auth_bp.get("/login")
def login() -> Response | tuple[Response, int]:
    """Render the appropriate login page."""
    try:
        controller = AuthController(get_manager())
    except RuntimeError:
        abort(501, description=_NON_MANAGED_ERROR)
    return controller.begin_oidc_login()

@auth_bp.post("/login")
def internal_login() -> Response | tuple[Response, int]:
    """Authenticate internal credentials and set the session cookie."""
    controller = AuthController(get_manager())
    return controller.gui_login(request.get_json(silent=True))

@auth_bp.get("/callback")
def call_back() -> WerkzeugResponse:
    """Handle the callback from the OIDC provider."""
    controller = AuthController(get_manager())
    return controller.oidc_callback()
