"""Authentication decorators for the Flask application.

.. module_author:: Rémi Verschuur <rverschuur@audit-io.fr>
.. version:: 1.0.0
"""
from __future__ import annotations

from collections.abc import Callable
from functools import wraps
from typing import ParamSpec, TypeVar, cast

from flask import abort, current_app, g, request

from auth.manager import AuthManager
from auth.models import UnifiedUser

P = ParamSpec("P")
R = TypeVar("R")


def require_authenticated_user(view: Callable[P, R]) -> Callable[P, R]:
    """Need an authenticated user to access the view.
    
    :param view: The view function that requires an authenticated user.
    :type view: Callable[P, R]
    :return: The wrapped view function.
    :rtype: Callable[P, R]
    """

    @wraps(view)
    def wrapped(*args: P.args, **kwargs: P.kwargs) -> R:
        """Wrapped view function that ensures an authenticated user."""
        authorization = request.headers.get("Authorization")

        if authorization is not None:
            scheme, separator, credentials = authorization.partition(" ")
            if scheme.lower() != "bearer" or not separator or not credentials.strip():
                abort(401)
            session_token = credentials.strip()
        else:
            cookie_name = cast(str, current_app.config["AUTH_COOKIE_NAME"])
            session_token = request.cookies.get(cookie_name)

        auth_manager = cast(
            AuthManager | None,
            current_app.extensions.get("auth_manager"),
        )
        user = (
            auth_manager.get_current_user(session_token)
            if auth_manager is not None
            else None
        )
        if user is None:
            abort(401)

        g.current_user = user
        return view(*args, **kwargs)

    return wrapped


def get_authenticated_user() -> UnifiedUser:
    """Retourne l'utilisateur authentifié associé à la requête."""
    return cast(UnifiedUser, g.current_user)


def require_admin(view: Callable[P, R]) -> Callable[P, R]:
    """Authenticate and check current persisted administrator privileges."""
    @require_authenticated_user
    @wraps(view)
    def wrapped(*args: P.args, **kwargs: P.kwargs) -> R:
        if not get_authenticated_user().is_admin:
            abort(403)
        return view(*args, **kwargs)

    return wrapped
