"""Backend OpenID Connect based on Authlib.

.. classes::
    - `OIDCAuthBackend`: Handles authentication via an OpenID Connect provider.

.. module_author:: Rémi Verschuur <rverschuur@audit-io.fr>
.. version:: 1.0.0
"""

from __future__ import annotations

import logging
from importlib import import_module
from dataclasses import dataclass
from typing import Any

from flask import Flask, Response

from auth.backends.base import AuthBackend
from auth.models import User
from auth.services import SessionService, UserService

LOGGER = logging.getLogger(__name__)
OIDC_REQUEST_TIMEOUT_SECONDS = 10

@dataclass
class OIDCConfig:
    """Configuration for the OIDC authentication backend.

    :param issuer: The OpenID Connect issuer URL.
    :type issuer: str
    :param client_id: The client ID for the OpenID Connect provider.
    :type client_id: str
    :param client_secret: The client secret for the OpenID Connect provider.
    :type client_secret: str
    :param redirect_uri: The redirect URI for the OpenID Connect provider.
    :type redirect_uri: str
    """
    issuer: str
    client_id: str
    client_secret: str
    redirect_uri: str



class OIDCAuthBackend(AuthBackend):
    """Handles authentication via an OpenID Connect provider.
    
    :param app: The Flask application instance.
    :type app: Flask
    :type config: OIDCConfig
    :param user_service: The service managing user data.
    :type user_service: UserService
    :param session_service: The service managing session data.
    :type session_service: SessionService
    :param user_service: The service managing user data.
    :type user_service: UserService
    :param session_service: The service managing session data.
    :type session_service: SessionService

    :raises ValueError: If the OIDC provider does not return a user profile.

    :return: The authenticated user.
    :rtype: User

    .. methods::
        - `authenticate`: Authenticates a user based on provided credentials.
        - `begin_login`: Initiates the login process by redirecting to the OIDC provider.
        - `complete_login`: Completes the login process and returns the authenticated user.
        - `get_current_user`: Retrieves the currently authenticated user based on the session token.
        - `logout`: Logs out the user by deleting the session token.

    .. author: Rémi Verschuur <rverschuur@audit-io.fr>
    .. version:: 1.0.0
    """

    def __init__(
        self,
        app: Flask,
        config: OIDCConfig,
        user_service: UserService,
        session_service: SessionService,
    ) -> None:
        """Initializes the OIDC authentication backend with the given configuration and services.

        :param app: The Flask application instance.
        :type app: Flask
        :param config: The OIDC configuration object containing issuer, client ID, client secret,
        and redirect URI.
        :type config: OIDCConfig
        :param user_service: The service managing user data.
        :type user_service: UserService
        :param session_service: The service managing session data.
        :type session_service: SessionService
        """
        oauth_class = import_module("authlib.integrations.flask_client").OAuth
        oauth: Any = oauth_class(app)
        self.client: Any = oauth.register(
            name="ttl-lama",
            client_id=config.client_id,
            client_secret=config.client_secret,
            server_metadata_url=f"{config.issuer.rstrip('/')}/.well-known/openid-configuration",
            client_kwargs={
                "scope": "openid profile email",
                "default_timeout": OIDC_REQUEST_TIMEOUT_SECONDS,
            },
        )
        self.issuer = config.issuer
        self.redirect_uri = config.redirect_uri
        self.user_service = user_service
        self.session_service = session_service

    def authenticate(self, credentials: dict[str, object] | None = None) -> None:
        """Authenticates a user based on provided credentials.

        :param credentials: The credentials provided for authentication.
        :type credentials: dict[str, object] | None

        :return: None
        """
        del credentials
        LOGGER.debug("Authenticate called with OIDCAuthBackend")

    def begin_login(self) -> Response:
        """Initiates the login process by redirecting to the OIDC provider.

        :return: A Flask response object that redirects the user to the OIDC provider's login page.
        :rtype: Response
        """
        LOGGER.debug("Beginning login with OIDCAuthBackend")
        return self.client.authorize_redirect(self.redirect_uri)

    def complete_login(self) -> User:
        """Completes the login process by exchanging the authorization code for an access token
        and retrieving the user profile.

        :return: The authenticated user.
        :rtype: User
        :raises ValueError: If the OIDC provider does not return a user profile.
        """
        token = self.client.authorize_access_token()
        claims: dict[str, Any] | None = token.get("userinfo")
        if claims is None:
            claims = self.client.userinfo(token=token)
        if claims is None:
            LOGGER.exception("No user profile returned by OIDC provider")
            raise ValueError("Le fournisseur OIDC n'a pas retourne de profil utilisateur")
        LOGGER.debug("User profile retrieved from OIDC provider: %s", claims)
        return self.user_service.sync_external_user(self.issuer, claims)

    def get_current_user(self, session_token: str | None = None) -> User | None:
        """Retrieves the currently authenticated user based on the session token.

        :param session_token: The session token associated with the user's session.
        :type session_token: str | None

        :return: The currently authenticated user, or None if no user is associated
        with the session token.
        :rtype: User | None
        """
        LOGGER.debug(
            "Retrieving current user with OIDCAuthBackend for session token: %s",
            session_token,
        )
        user_id = self.session_service.get_user_id(session_token)
        return self.user_service.get(user_id) if user_id is not None else None

    def logout(self, session_token: str | None = None) -> None:
        """Logs out the user by deleting the session token.

        :param session_token: The session token associated with the user's session.
        :type session_token: str | None

        :return: None
        """
        LOGGER.debug(
            "Logging out with OIDCAuthBackend for session token: %s",
            session_token,
        )
        self.session_service.delete(session_token)
