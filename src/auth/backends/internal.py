"""Internal authentication backend for the TTL-LAMa database.

.. classes::
    - `InternalAuthBackend`: Authenticate users against the internal database.

.. module_author:: Rémi Verschuur <rverschuur@audit-io.fr>
.. version:: 1.0.0
"""
from __future__ import annotations

import logging

from auth.backends.base import AuthBackend
from auth.models import User
from auth.services import SessionService, UserService

LOGGER = logging.getLogger(__name__)

class InternalAuthBackend(AuthBackend):
    """Authenticate users and resolve their persistent sessions.

    :param user_service: Service for managing user data.
    :type user_service: UserService
    :param session_service: Service for managing user sessions.
    :type session_service: SessionService
    :return: None
    :rtype: None

    .. methods::
        - `__init__`: Initialize the backend with user and session services.
        - `authenticate`: Authenticate a user with given credentials.
        - `get_current_user`: Retrieve the current user based on session token.
        - `logout`: Logout the current session.

    .. author:: Rémi Verschuur <rverschuur@audit-io.fr>
    .. version:: 1.0.0
    """

    def __init__(self, user_service: UserService, session_service: SessionService) -> None:
        """Initialize the backend with user and session services.

        :param user_service: Service for managing user data.
        :type user_service: UserService
        :param session_service: Service for managing user sessions.
        :type session_service: SessionService
        :return: None
        :rtype: None
        """
        self.user_service = user_service
        self.session_service = session_service

    def authenticate(self, credentials: dict[str, object] | None = None) -> User | None:
        """Authenticate a user with given credentials.

        :param credentials: Dictionary containing 'username' and 'password'.
        :type credentials: dict[str, object] | None
        :return: Authenticated user or None if authentication fails.
        :rtype: User | None
        """
        username = credentials.get("username") if credentials is not None else None
        password = credentials.get("password") if credentials is not None else None
        if not isinstance(username, str):
            username = None
        if not isinstance(password, str):
            password = None
        LOGGER.debug("Attempting internal authentication")
        return self.user_service.authenticate(username, password)

    def get_current_user(self, session_token: str | None = None) -> User | None:
        """Retrieve the current user based on session token.

        :param session_token: Session token of the current session.
        :type session_token: str | None
        :return: Current user or None if session is invalid.
        :rtype: User | None
        """
        user_id = self.session_service.get_user_id(session_token)
        return self.user_service.get(user_id) if user_id is not None else None

    def logout(self, session_token: str | None = None) -> None:
        """Logout the current session.

        :param session_token: Session token of the current session.
        :type session_token: str | None
        :return: None
        :rtype: None
        """
        self.session_service.delete(session_token)
