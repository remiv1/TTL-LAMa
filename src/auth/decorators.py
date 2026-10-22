"""Authentification decorators and authorization of routes.

.. functions::
    - `get_current_user`: Retrieves the current user, cached for the request.
    - `require_auth`: Decorator to require authentication for a route.
    - `require_group`: Decorator to require a specific group for a route.

.. module_author:: Rémi Verschuur <rverschuur@audit-io.fr>
.. version:: 1.0.0
"""
from __future__ import annotations

import logging
from functools import wraps
from typing import Any, Callable

from flask import abort, current_app, g, request

from auth.manager import AuthManager
from auth.models import User

LOGGER = logging.getLogger(__name__)
ROLE_LEVELS = {
    "VIEWER": 0,
    "EDITOR": 1,
    "ADMIN": 2
}

def get_current_user() -> User | None:
    """Returns the current user, cached for the request.

    :return: The current user, or None if no user is authenticated.
    :rtype: User | None
    """
    if not hasattr(g, "auth_user"):
        manager: AuthManager = current_app.extensions["auth_manager"]
        g.auth_user = manager.get_current_user(
            request.cookies.get(manager.settings.AUTH_COOKIE_NAME)
        )
    return g.auth_user


def require_auth(view: Callable[..., Any]) -> Callable[..., Any]:
    """Refuse the request when no user is authenticated.

    :param view: The view function to decorate.
    :type view: Callable[..., Any]

    :return: The decorated view function.
    :rtype: Callable[..., Any]

    :raises werkzeug.exceptions.Unauthorized: If no user is authenticated.
    """

    @wraps(view)
    def wrapped(*args: Any, **kwargs: Any) -> Any:
        """Require a current user before invoking the decorated view.

        :param args: Positional arguments passed to the view.
        :type args: Any
        :param kwargs: Keyword arguments passed to the view.
        :type kwargs: Any
        :returns: The decorated view's result.
        :rtype: Any
        :raises werkzeug.exceptions.Unauthorized: If no user is authenticated.
        """
        if get_current_user() is None:
            abort(401)
        return view(*args, **kwargs)

    return wrapped


def require_group(group: str) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """Reject requests from users who lack the required group.

    :param group: The required group for the route.
    :type group: str

    :return: The decorator function.
    :rtype: Callable[[Callable[..., Any]], Callable[..., Any]]

    :raises 401: If no user is authenticated.
    :raises 403: If the user does not have the required group.
    """

    def decorate(view: Callable[..., Any]) -> Callable[..., Any]:
        """Wrap a view with the group authorization check.

        :param view: The route function to decorate.
        :type view: Callable[..., Any]
        :returns: The decorated route function.
        :rtype: Callable[..., Any]
        """

        @wraps(view)
        def wrapped(*args: Any, **kwargs: Any) -> Any:
            """Require authentication and membership before invoking the view.

            :param args: Positional arguments passed to the view.
            :type args: Any
            :param kwargs: Keyword arguments passed to the view.
            :type kwargs: Any
            :returns: The decorated view's result.
            :rtype: Any
            :raises werkzeug.exceptions.Unauthorized: If no user is authenticated.
            :raises werkzeug.exceptions.Forbidden: If the user lacks the required group.
            """
            user = get_current_user()
            if user is None:
                abort(401)
            required_level = ROLE_LEVELS.get(group)
            has_group = (
                any(ROLE_LEVELS.get(user_group, -1) >= required_level for user_group in user.groups)
                if required_level is not None
                else group in user.groups
            )
            if not has_group:
                abort(403)
            return view(*args, **kwargs)

        return wrapped

    return decorate
