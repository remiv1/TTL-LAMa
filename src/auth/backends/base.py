"""Base authentication backend.

.. classes::
    - `AuthBackend`: Base class for all authentication backends.

.. author:: Rémi Verschuur <rverschuur@audit-io.fr>
.. version:: 1.0
"""
from __future__ import annotations

from abc import ABC, abstractmethod

from flask import Response

from auth.models import User


class AuthBackend(ABC):
    """Base class for all authentication backends.
    .. methods::
        - `authenticate`: Authenticate a user with given credentials.
        - `get_current_user`: Retrieve the current user based on session token.
        - `logout`: Logout the current session.
        - `begin_login`: Start an interactive login flow if supported by the backend.
        - `complete_login`: Complete an interactive login flow if supported by the backend.

    .. author:: Rémi Verschuur <rverschuur@audit-io.fr>
    .. version:: 1.0
    """

    @abstractmethod
    def authenticate(self, credentials: dict[str, object] | None = None) -> User | None:
        """Authenticate credentials provided by the user.
        
        :param credentials: Dictionary containing the user's credentials.
        :type credentials: dict[str, object] | None
        :return: The authenticated user or None if authentication fails.
        :rtype: User | None
        """

    @abstractmethod
    def get_current_user(self, session_token: str | None = None) -> User | None:
        """Return the identity associated with the current session.
        
        :param session_token: Session token to identify the current user.
        :type session_token: str | None
        :return: The current user or None if no session is active.
        :rtype: User | None
        """

    @abstractmethod
    def logout(self, session_token: str | None = None) -> None:
        """Revoke the current session if it exists.
        
        :param session_token: Session token to revoke.
        :type session_token: str | None
        :return: None
        :rtype: None
        """

    def begin_login(self) -> Response | None:
        """Start an interactive login flow if supported by the backend.

        :return: A Flask Response object to continue the login flow, or None if not supported.
        :rtype: Response | None
        """
        return None

    def complete_login(self) -> User:
        """Complete an interactive login flow if supported by the backend.

        :return: The authenticated user after completing the login flow.
        :rtype: User
        """
        raise NotImplementedError
