"""OpenID Connect (OIDC) authentication backend.

.. author:: Rémi Verschuur <rverschuur@audit-io.fr>
.. version:: 1.0
"""
from __future__ import annotations

from collections.abc import Mapping
from typing import Protocol, cast

from flask import Response
from joserfc.errors import JoseError
from requests import post
from requests.auth import HTTPBasicAuth
from requests.exceptions import RequestException

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

    def load_server_metadata(self) -> dict[str, object]:
        """Load provider metadata."""
        ... # pylint: disable=W2301

    def userinfo(self, **kwargs: object) -> Mapping[str, object]:
        """Fetch and validate user information using an access token."""
        ... # pylint: disable=W2301

    def parse_id_token(
        self,
        token: dict[str, object],
        nonce: str | None,
    ) -> Mapping[str, object] | None:
        """Validate an ID token and return its claims."""
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
        return self._user_from_claims(token.get("userinfo"))

    def begin_device_authorization(
        self,
        client_id: str,
        client_secret: str,
    ) -> dict[str, object]:
        """Start a device authorization request with the configured provider."""
        metadata = self.oidc_client.load_server_metadata()
        endpoint = metadata.get("device_authorization_endpoint")
        if not isinstance(endpoint, str):
            raise OIDCAuthenticationError(
                "The OIDC provider does not support device authorization."
            )

        try:
            response = post(
                endpoint,
                data={"client_id": client_id, "scope": "openid"},
                auth=HTTPBasicAuth(client_id, client_secret),
                timeout=10,
            )
            raw_payload = response.json()
        except (RequestException, ValueError) as error:
            raise OIDCAuthenticationError(
                "Unable to start OIDC device authorization."
            ) from error

        if response.status_code >= 400 or not isinstance(raw_payload, dict):
            raise OIDCAuthenticationError(
                "The OIDC provider rejected device authorization."
            )
        payload = cast(dict[str, object], raw_payload)

        device_code = payload.get("device_code")
        user_code = payload.get("user_code")
        verification_uri = payload.get("verification_uri")
        expires_in = payload.get("expires_in")
        interval = payload.get("interval", 5)
        if (
            not isinstance(device_code, str)
            or not device_code
            or not isinstance(user_code, str)
            or not user_code
            or not isinstance(verification_uri, str)
            or not verification_uri
            or not isinstance(expires_in, int)
            or expires_in <= 0
            or not isinstance(interval, int)
            or interval <= 0
        ):
            raise OIDCAuthenticationError(
                "The OIDC provider returned an invalid device authorization response."
            )

        result: dict[str, object] = {
            "device_code": device_code,
            "user_code": user_code,
            "verification_uri": verification_uri,
            "expires_in": expires_in,
            "interval": interval,
        }
        verification_uri_complete = payload.get("verification_uri_complete")
        if isinstance(verification_uri_complete, str):
            result["verification_uri_complete"] = verification_uri_complete
        return result

    def poll_device_authorization(
        self,
        device_code: str,
        client_id: str,
        client_secret: str,
    ) -> dict[str, object]:
        """Poll the provider and resolve the approved identity."""
        metadata = self.oidc_client.load_server_metadata()
        endpoint = metadata.get("token_endpoint")
        if not isinstance(endpoint, str):
            raise OIDCAuthenticationError("The OIDC token endpoint is unavailable.")

        try:
            response = post(
                endpoint,
                data={
                    "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
                    "device_code": device_code,
                    "client_id": client_id,
                },
                auth=HTTPBasicAuth(client_id, client_secret),
                timeout=10,
            )
            raw_payload = response.json()
        except (RequestException, ValueError) as error:
            raise OIDCAuthenticationError(
                "Unable to poll OIDC device authorization."
            ) from error

        if not isinstance(raw_payload, dict):
            raise OIDCAuthenticationError(
                "The OIDC provider returned an invalid device response."
            )
        payload = cast(dict[str, object], raw_payload)

        if response.status_code >= 400:
            provider_error = payload.get("error")
            status_by_error = {
                "authorization_pending": "pending",
                "slow_down": "slow_down",
                "access_denied": "denied",
                "expired_token": "expired",
            }
            status = (
                status_by_error.get(provider_error)
                if isinstance(provider_error, str)
                else None
            )
            if status is not None:
                return {"status": status}
            raise OIDCAuthenticationError(
                "The OIDC provider rejected device authorization."
            )

        if not isinstance(payload.get("access_token"), str):
            raise OIDCAuthenticationError(
                "The OIDC provider returned no access token."
            )
        try:
            user_info = self.oidc_client.parse_id_token(payload, nonce=None)
        except (JoseError, RequestException, ValueError) as error:
            raise OIDCAuthenticationError(
                "Unable to verify the OIDC device identity."
            ) from error
        if user_info is None:
            raise OIDCAuthenticationError(
                "The OIDC provider returned no ID token for device authorization."
            )
        return {"status": "complete", "user": self._user_from_claims(user_info)}

    def _user_from_claims(self, user_info: object) -> UnifiedUser:
        """Resolve validated OIDC claims to an enabled local account."""

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
