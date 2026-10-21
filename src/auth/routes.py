"""REST routes of the authentication session lifecycle.

.. routes::
    - `/auth/csrf`: Retourne un jeton CSRF pour les clients utilisant les sessions cookie.
    - `/auth/me`: Expose l'identite uniforme liee a la requete.
    - `/auth/login`: Demarre OIDC ou authentifie un utilisateur interne.
    - `/auth/callback`: Finalise le flux OIDC et cree une session TTL-LAMa.
    - `/auth/logout`: Revoque la session courante et supprime son cookie.

.. module_author:: Rémi Verschuur <rverschuur@audit-io.fr>
.. version:: 1.0.0
"""
from __future__ import annotations

from typing import cast
import logging

from flask import (
    Blueprint,
    current_app,
    jsonify,
    make_response,
    redirect,
    request,
    Response,
    session,
)
from flask_wtf.csrf import generate_csrf
from authlib.integrations.base_client.errors import OAuthError
from joserfc.errors import BadSignatureError
from requests.exceptions import RequestException

from auth.decorators import get_current_user, require_auth
from auth.manager import AuthManager

auth_bp = Blueprint("auth", __name__, url_prefix="/auth")
LOGGER = logging.getLogger(__name__)

@auth_bp.get("/csrf")
def csrf_token() -> Response:
    """Returns a CSRF token for clients using cookie-based sessions.
    
    :return: JSON containing the CSRF token.
    :rtype: dict[str, str]
    """
    return jsonify(csrf_token=generate_csrf())


@auth_bp.get("/me")
@require_auth
def current_user() -> Response | tuple[Response, int]:
    """Exposes the uniform identity associated with the request.
    
    :return: JSON containing the current user or an error if not authenticated.
    :rtype: dict[str, object] | tuple[dict[str, str], int]
    """
    user = get_current_user()
    if user is None:
        return jsonify(error="Authentication required"), 401
    return jsonify(user=user.to_dict())


@auth_bp.route("/login", methods=["GET", "POST"])
def login() -> Response | tuple[Response, int]:
    """Start OIDC or authenticate an internal user.
    
    :return: JSON containing the authenticated user or an error.
    :rtype: dict[str, object] | tuple[dict[str, str], int]
    """
    manager: AuthManager = current_app.extensions["auth_manager"]
    if request.method == "GET":
        if manager.mode == "external":
            try:
                response = manager.begin_login()
            except (ConnectionError, TimeoutError, RequestException):
                LOGGER.warning("OIDC provider is unavailable during login initialization")
                return jsonify(error="Identity provider temporarily unavailable"), 503
            if response is not None:
                return response
        return jsonify(error="Interactive login is not available in this mode"), 405
    if manager.mode == "none":
        return jsonify(error="Login is disabled in none mode"), 405
    if manager.mode == "external":
        return jsonify(error="Use GET /auth/login for OIDC authentication"), 405
    credentials = request.get_json(silent=True)
    result = manager.authenticate(
        cast(
            dict[str, object], credentials
            if isinstance(credentials, dict)
            else {}
        )
    )
    if result is None:
        return jsonify(error="Invalid username or password"), 401
    user, token = result
    response = make_response(jsonify(user=user.to_dict()))
    if token is not None:
        response.set_cookie(
            manager.settings.AUTH_COOKIE_NAME,
            token,
            max_age=int(manager.sessions.lifetime.total_seconds()),
            httponly=True,
            secure=manager.settings.ENFORCE_SECURE_CONNECTION,
            samesite="Lax",
            path="/",
        )
    return response


@auth_bp.get("/callback")
def oidc_callback() -> Response | tuple[Response, int]:
    """Finalizes the OIDC flow and creates a TTL-LAMa session.
    
    :return: JSON containing the authenticated user or an error.
    :rtype: dict[str, object] | tuple[dict[str, str], int]

    :raises OAuthError: If the OIDC authentication fails.
    :raises ValueError: If there is an issue with the OIDC response.
    :raises KeyError: If expected keys are missing in the OIDC response.
    """
    manager: AuthManager = current_app.extensions["auth_manager"]
    if manager.mode != "external":
        LOGGER.warning("OIDC attempted while not in external mode")
        return jsonify(error="OIDC is not enabled"), 404
    try:
        user, token = manager.complete_login()
    except (ConnectionError, TimeoutError, RequestException):
        LOGGER.exception("OIDC provider is unavailable during callback")
        return jsonify(error="Identity provider temporarily unavailable"), 503
    except (OAuthError, BadSignatureError, ValueError, KeyError):
        LOGGER.exception("OIDC authentication failed")
        return jsonify(error="OIDC authentication failed"), 401
    response = (
        make_response(redirect("/"))
        if session.pop("web_login", False)
        else make_response(jsonify(user=user.to_dict()))
    )
    response.set_cookie(
        manager.settings.AUTH_COOKIE_NAME,
        token,
        max_age=int(manager.sessions.lifetime.total_seconds()),
        httponly=True,
        secure=manager.settings.ENFORCE_SECURE_CONNECTION,
        samesite="Lax",
        path="/",
    )
    return response


@auth_bp.post("/logout")
def logout() -> Response:
    """Revokes the current session and deletes its cookie.
    
    :return: JSON indicating the success of the operation.
    :rtype: dict[str, bool]
    """
    manager: AuthManager = current_app.extensions["auth_manager"]
    manager.logout(request.cookies.get(manager.settings.AUTH_COOKIE_NAME))
    response = make_response(jsonify(success=True))
    response.delete_cookie(
        manager.settings.AUTH_COOKIE_NAME,
        httponly=True,
        secure=manager.settings.ENFORCE_SECURE_CONNECTION,
        samesite="Lax",
        path="/",
    )
    return response
