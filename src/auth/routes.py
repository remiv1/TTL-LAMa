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

from typing import cast

from flask import Blueprint, Response, abort, current_app, redirect, request, url_for
from werkzeug import Response as WerkzeugResponse

from auth.controller import AuthController
from auth.manager import get_manager

_NON_MANAGED_ERROR = "Authentication manager not configured."

auth_bp = Blueprint("auth", __name__, url_prefix="/auth")

@auth_bp.get("/login")
def login() -> WerkzeugResponse | tuple[Response, int]:
    """Render the appropriate login page."""
    config = cast(dict[str, object], current_app.config)
    if config.get("AUTH_MODE") == "internal":
        return redirect(url_for("web.login"))
    try:
        controller = AuthController(get_manager())
    except RuntimeError:
        abort(501, description=_NON_MANAGED_ERROR)
    return controller.begin_oidc_login()

@auth_bp.post("/login")
def internal_login() -> WerkzeugResponse | tuple[Response, int]:
    """Authenticate internal credentials and set the session cookie."""
    controller = AuthController(get_manager())
    if request.is_json:
        return controller.gui_login(request.get_json(silent=True))

    result = controller.gui_login(request.form.to_dict())
    if isinstance(result, tuple):
        response, status = result
    else:
        response, status = result, result.status_code

    if status != 200:
        return redirect(url_for("web.login", error="invalid"), code=303)

    response.set_data(b"")
    response.status_code = 303
    response.headers["Location"] = url_for("web.index")
    return response

@auth_bp.get("/callback")
def call_back() -> WerkzeugResponse:
    """Handle the callback from the OIDC provider."""
    controller = AuthController(get_manager())
    return controller.oidc_callback()
