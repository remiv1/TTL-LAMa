"""OpenID Connect (OIDC) authentication backend.

.. author:: Rémi Verschuur <rverschuur@audit-io.fr>
.. version:: 1.0
"""
from __future__ import annotations

from collections.abc import Mapping
from typing import Protocol, cast

from flask import Response

from auth.backends.base import AuthBackend
from auth.models import UnifiedUser, OIDCParams
from auth.services import UserService
from auth.exceptions import AccountNotFoundError, OIDCAuthenticationError

class _OIDCClient(Protocol):    # pylint: disable=R0903
    """Protocol for OIDC client."""
    def authorize_redirect(self, redirect_uri: str) -> Response:
        """Authorize a redirect to the OIDC provider's login page."""
        ... # pylint: disable=W2301

    def authorize_access_token(self) -> dict[str, object]:
        """Authorize and retrieve an access token from the OIDC provider."""
        ... # pylint: disable=W2301


class OIDCAuthBackend(AuthBackend):
    """OIDC authentication backend.

    .. methods::
        - `authenticate`: Authenticate a user with given credentials.
        - `get_current_user`: Retrieve the current user based on session token.
        - `logout`: Logout the current session.
        - `begin_login`: Start an interactive login flow if supported by the backend.
        - `complete_login`: Complete an interactive login flow if supported by the backend.

    .. author:: Rémi Verschuur <rverschuur@audit-io.fr>
    .. version:: 1.0.0
    """
    def __init__(
        self,
        user_service: UserService,
        oidc_params: OIDCParams,
    ) -> None:
        self.oidc_client = cast(_OIDCClient, oidc_params.oidc_client)
        self.user_service = user_service
        self.issuer = oidc_params.issuer
        self.redirect_uri = oidc_params.redirect_uri

    def authenticate(self, credentials: dict[str, object] | None = None) -> UnifiedUser | None:
        """Signale that this backend doesn't support authentication via credentials.

        :param credentials: Dictionary containing the user's credentials.
        :type credentials: dict[str, object] | None

        :return: Always raises NotImplementedError as this backend doesn't support credential-based
        authentication.
        :rtype: NoReturn

        :raises NotImplementedError: Always raised as this backend doesn't support credential-based
        authentication.
        """
        raise NotImplementedError("OIDC backend does not support credential-based authentication.")

    def begin_login(self) -> Response:
        """Start an interactive login flow for OIDC.

        :return: A Flask response to redirect the user to the OIDC provider's login page.
        :rtype: Response
        """
        return self.oidc_client.authorize_redirect(self.redirect_uri)

    def complete_login(self) -> UnifiedUser:
        """Complete an interactive login flow for OIDC.

        :return: The authenticated user.
        :rtype: UnifiedUser

        :raises OIDCAuthenticationError: If the login flow could not be completed successfully.
        """
        token = self.oidc_client.authorize_access_token()
        user_info = token.get("userinfo")

        if not isinstance(user_info, Mapping):
            raise OIDCAuthenticationError("Failed to retrieve user info from OIDC provider.")

        claims = cast(Mapping[str, object], user_info)
        subject = claims.get("sub")
        if not isinstance(subject, str) or not subject.strip():
            raise OIDCAuthenticationError("Invalid subject in user info from OIDC provider.")

        user = self.user_service.get_by_oidc(self.issuer, subject)
        if user is None:
            raise AccountNotFoundError("No account found for the given OIDC subject.")
        if not user.enabled:
            raise OIDCAuthenticationError(
                "The account associated with the OIDC subject is not enabled.",
            )

        return UnifiedUser.from_db_user(user)
