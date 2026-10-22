"""Central selection and orchestration of authentication backends.

.. classes::
    - `AuthManager`: Central selection and orchestration of authentication backends.

.. module_author:: Rémi Verschuur <rverschuur@audit-io.fr>
.. version:: 1.0.0
"""
from __future__ import annotations

import logging
from typing import Literal

from flask import Flask, Response, current_app
from sqlalchemy.orm import Session, scoped_session

from auth.backends import AuthBackend, InternalAuthBackend
from auth.models import User
from auth.services import SessionService, UserService
from api.config import FlaskSettings

AuthMode = Literal["internal", "external"]
LOGGER = logging.getLogger(__name__)

class AuthManager:
    """Select and orchestrate the backend configured for the application.

    :param app: The Flask application instance.
    :type app: Flask
    :param db_session: The scoped session for database interactions.
    :type db_session: scoped_session[Session]
    :param settings: The Flask application settings containing authentication configuration.
    :type settings: FlaskSettings

    .. methods::
        - `get_backend`: Returns the current authentication backend.
        - `initialize_database`: Initializes the database with initial groups
        and admin user if necessary.
        - `authenticate`: Authenticates a user based on provided credentials.
        - `begin_login`: Initiates the login process by redirecting to the OIDC provider.
        - `complete_login`: Completes the login process and returns the authenticated user.
        - `get_current_user`: Retrieves the currently authenticated user based on the session token.
        - `logout`: Logs out the user by deleting the session token.
        - `_create_backend`: Internal method to create the appropriate authentication backend
        based on the current mode.

    .. author:: Rémi Verschuur <rverschuur@audit-io.fr>
    .. version:: 1.0.0
    """

    def __init__(
        self,
        app: Flask,
        db_session: scoped_session[Session],
        settings: FlaskSettings,
    ) -> None:
        """Initializes the AuthManager with the given Flask application, database session,
        and settings.

        :param app: The Flask application instance.
        :type app: Flask
        :param db_session: The scoped session for database interactions.
        :type db_session: scoped_session[Session]
        :param settings: The Flask application settings containing authentication configuration.
        :type settings: FlaskSettings
        """
        self.app = app
        self.settings = settings
        self.mode: AuthMode = settings.AUTH_MODE
        self.sessions = SessionService(db_session)
        self.users = UserService(db_session)
        self.backend = self._create_backend()

    @classmethod
    def get_backend(cls) -> AuthBackend:
        """Returns the current backend without exposing its construction to the blueprints.
        
        :return: The current authentication backend.
        :rtype: AuthBackend
        """
        return current_app.extensions["auth_manager"].backend

    @classmethod
    def initialize_database(
        cls,
        db_session: scoped_session[Session],
        settings: FlaskSettings,
    ) -> None:
        """Creates the initial groups and administrator when necessary.

        :param db_session: Scoped SQLAlchemy session used for initialization.
        :type db_session: scoped_session[Session]
        :param settings: Validated application settings.
        :type settings: FlaskSettings
        :returns: ``None``.
        :rtype: None
        """
        service = UserService(db_session)
        service.synchronize_auth_context(
            settings.AUTH_MODE,
            settings.OIDC_ISSUER if settings.AUTH_MODE == "external" else None,
        )
        if settings.AUTH_MODE == "internal":
            service.ensure_identity_records()
            service.ensure_initial_admin(settings.ADMIN_USERNAME, settings.ADMIN_PASSWORD)
        elif settings.AUTH_MODE == "external":
            service.ensure_groups()
            service.ensure_identity_records()
        service.ensure_login_states()

    def authenticate(
        self,
        credentials: dict[str, object] | None = None,
    ) -> tuple[User, str] | None:
        """Authenticate credentials and create a persistent session on success.

        :param credentials: The credentials provided for authentication.
        :type credentials: dict[str, object] | None

        :returns: The authenticated user and session token, or ``None`` on failure.
        :rtype: tuple[User, str] | None
        """
        user = self.backend.authenticate(credentials)
        if user is None:
            LOGGER.warning("Authentication failed")
            return None
        token = self.sessions.create(int(user.id))
        return user, token

    def complete_login(self) -> tuple[User, str]:
        """Complete OIDC authentication and create a TTL-LAMa session.

        :returns: The authenticated user and its session token.
        :rtype: tuple[User, str]
        """
        user = self.backend.complete_login()
        return user, self.sessions.create(int(user.id))

    def get_current_user(self, session_token: str | None = None) -> User | None:
        """Retrieve the current user through the configured backend.

        :param session_token: The session token associated with the user's session.
        :type session_token: str | None

        :returns: The current user, or ``None`` when the token has no valid identity.
        :rtype: User | None
        """
        return self.backend.get_current_user(session_token)

    def logout(self, session_token: str | None = None) -> None:
        """Log out the current session.

        :param session_token: The session token associated with the user's session.
        :type session_token: str | None

        :returns: ``None``.
        :rtype: None
        """
        self.backend.logout(session_token)

    def begin_login(self) -> Response | None:
        """Start an interactive login flow when supported.

        :returns: A redirect response for external authentication, if supported.
        :rtype: Response | None
        """
        return self.backend.begin_login()

    def _create_backend(self) -> AuthBackend:
        """Instantiate the backend matching the configured authentication mode.

        :returns: The configured authentication backend.
        :rtype: AuthBackend
        """
        if self.mode == "internal":
            return InternalAuthBackend(self.users, self.sessions)
        from auth.backends.oidc import OIDCAuthBackend, OIDCConfig  # pylint: disable=C0415

        config = OIDCConfig(
            issuer=self.settings.OIDC_ISSUER,
            client_id=self.settings.OIDC_CLIENT_ID,
            client_secret=self.settings.OIDC_CLIENT_SECRET,
            redirect_uri=self.settings.OIDC_REDIRECT_URI,
        )

        return OIDCAuthBackend(
            app=self.app,
            config=config,
            user_service=self.users,
            session_service=self.sessions,
        )
