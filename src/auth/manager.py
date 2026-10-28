"""Orchestration for authentication management.

.. module_author:: Rémi Verschuur <rverschuur@audit-io.fr>
.. version:: 1.0.0
"""
from __future__ import annotations

from flask import Response, current_app

from auth.backends import AuthBackend
from auth.models import AuthenticationResult, UnifiedUser
from auth.services import SessionService, UserService

def get_manager() -> AuthManager:
    """Retrieve the current AuthManager instance from the Flask application context."""
    manager = current_app.extensions.get("auth_manager")
    if manager is None:
        raise RuntimeError("Authentication manager not configured.")
    return manager


class AuthManager:
    """Manages authentication by coordinating backends and services.
    
    :param backend: The authentication backend to use.
    :type backend: AuthBackend
    :param session_service: The session service to use.
    :type session_service: SessionService
    :param user_service: The user service to use.
    :type user_service: UserService
    """
    def __init__(
        self,
        backend: AuthBackend,
        session_service: SessionService,
        user_service: UserService,
    ) -> None:
        self.backend = backend
        self.session_service = session_service
        self.user_service = user_service

    def complete_login(self) -> AuthenticationResult:
        """Completes the login process by coordinating the backend and session service.

        :return: The result of the authentication process.
        :rtype: AuthenticationResult
        """
        user = self.backend.complete_login()
        session_token = self.session_service.create(user.id)

        return AuthenticationResult(
            user=user,
            session_token=session_token,
        )

    def authenticate(
        self,
        credentials: dict[str, object] | None = None,
    ) -> AuthenticationResult | None:
        """Authenticates a user with the given credentials.

        :param credentials: The credentials to use for authentication.
        :type credentials: dict[str, object] | None
        :return: The result of the authentication process, or None if authentication failed.
        :rtype: AuthenticationResult | None
        """
        user = self.backend.authenticate(credentials)
        if user is None:
            return None

        session_token = self.session_service.create(user.id)
        return AuthenticationResult(
            user=user,
            session_token=session_token,
        )

    def get_current_user(self, session_token: str | None) -> UnifiedUser | None:
        """Retourns the currently active user associated with a session token.
        
        :param session_token: The session token to use for retrieving the current user.
        :type session_token: str | None
        :return: The currently active user, or None if no active user is found.
        :rtype: UnifiedUser | None
        """
        user_id = self.session_service.get_user_id(session_token)
        if user_id is None:
            return None

        try:
            user = self.user_service.get_by_id(user_id)
        except ValueError:
            return None

        if not user.enabled:
            return None

        return UnifiedUser(
            id=str(user.id),
            username=user.username,
            is_admin=user.is_admin,
            email=user.email,
        )

    def begin_login(self) -> Response | None:
        """Initiates the login process delegating it to the backend.

        :return: The response that initiates the login process, or None if not applicable.
        :rtype: Response | None
        """
        return self.backend.begin_login()

    def logout(self, session_token: str | None) -> None:
        """Revokes the session associated with the given token.

        :param session_token: The session token to revoke.
        :type session_token: str | None
        """
        self.session_service.revoke(session_token)
