"""Module for authentication models.

.. author:: Rémi Verschuur <rverschuur@audit-io.fr>
.. version:: 1.0.0
"""
from __future__ import annotations

from dataclasses import dataclass, field

from authlib.integrations.flask_client.apps import FlaskOAuth2App

@dataclass
class UnifiedUser:
    """Represents a common user for authentication purposes.
    
    :param id: Unique identifier of the user.
    :type id: str
    :param username: Username of the user.
    :type username: str
    :param email: Email of the user.
    :type email: str | None
    :param is_admin: Indicates if the user has admin privileges.
    :type is_admin: bool
    """
    id: str
    username: str
    is_admin: bool
    email: str | None = None

@dataclass(frozen=True)
class AuthenticationResult:
    """Represents the result of an authentication attempt.

    :param user: The authenticated user.
    :type user: UnifiedUser
    :param session_token: The session token for the authenticated user.
    :type session_token: str
    """
    user: UnifiedUser
    session_token: str = field(repr=False)

@dataclass
class OIDCParams:
    """Represents an OIDC authentication request.

    :param oidc_client: The OIDC client for the request.
    :type oidc_client: FlaskOAuth2App
    :param redirect_uri: The redirect URI for the OIDC request.
    :type redirect_uri: str
    :param scope: The scope of the OIDC request.
    :type scope: str
    :param state: The state parameter for the OIDC request.
    :type state: str
    """
    oidc_client: FlaskOAuth2App
    issuer: str
    redirect_uri: str
