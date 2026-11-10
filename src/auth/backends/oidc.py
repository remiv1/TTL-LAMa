"""OpenID Connect (OIDC) authentication backend.

.. author:: Rémi Verschuur <rverschuur@audit-io.fr>
.. version:: 1.0
"""
from __future__ import annotations

from collections.abc import Mapping
import secrets
from typing import Protocol, cast

from authlib.integrations.base_client.errors import OAuthError
from flask import Response, session
from joserfc.errors import JoseError
from requests import post
from requests.auth import HTTPBasicAuth
from requests.exceptions import RequestException

from auth.backends.base import AuthBackend
from auth.models import UnifiedUser, OIDCParams
from auth.services import UserService
from auth.exceptions import OIDCAuthenticationError

class _OIDCFramework(Protocol):
    """Protocol for Authlib's Flask state storage adapter."""
    def get_state_data(self, session_data: object, state: str) -> object | None:
        """Get pending authorization data for a state value."""
        ... # pylint: disable=W2301

    def clear_state_data(self, session_data: object, state: str) -> None:
        """Remove pending authorization data for a state value."""
        ... # pylint: disable=W2301


class _OIDCClient(Protocol):    # pylint: disable=R0903
    """Protocol for OIDC client."""
    @property
    def framework(self) -> _OIDCFramework:
        """Return the framework adapter used to manage OAuth state."""
        ... # pylint: disable=W2301

    def authorize_redirect(self, redirect_uri: str, **kwargs: object) -> Response:
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
        initial_admin_username: str | None = None,
    ) -> None:
        self.oidc_client = cast(_OIDCClient, oidc_params.oidc_client)
        self.user_service = user_service
        self.issuer = oidc_params.issuer
        self.redirect_uri = oidc_params.redirect_uri
        self.initial_admin_username = initial_admin_username

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
        return self.oidc_client.authorize_redirect(
            self.redirect_uri,
            nonce=secrets.token_urlsafe(32),
        )

    def complete_login(self) -> UnifiedUser:
        """Complete an interactive login flow for OIDC.

        :return: The authenticated user.
        :rtype: UnifiedUser

        :raises OIDCAuthenticationError: If the login flow could not be completed successfully.
        """
        try:
            token = self.oidc_client.authorize_access_token()
        except (OAuthError, JoseError, RequestException, ValueError, KeyError) as error:
            raise OIDCAuthenticationError(
                "Unable to complete OIDC authentication."
            ) from error
        return self._user_from_claims(token.get("userinfo"), allow_first_link=True)

    def validate_error_state(self, state: object) -> bool:
        """Validate and consume Authlib state when the provider returns an error."""
        if not isinstance(state, str) or not state:
            return False

        framework = self.oidc_client.framework
        if framework.get_state_data(session, state) is None:
            return False

        framework.clear_state_data(session, state)
        return True

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
                data={
                    "client_id": client_id,
                    "client_secret": client_secret,
                    "scope": "openid profile",
                },
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
        except (OAuthError, JoseError, RequestException, ValueError, KeyError) as error:
            raise OIDCAuthenticationError(
                "Unable to verify the OIDC device identity."
            ) from error
        if user_info is None:
            raise OIDCAuthenticationError(
                "The OIDC provider returned no ID token for device authorization."
            )
        return {
            "status": "complete",
            "user": self._user_from_claims(user_info, allow_first_link=True),
        }

    def _user_from_claims(
        self,
        user_info: object,
        *,
        allow_first_link: bool = False,
    ) -> UnifiedUser:
        """Resolve validated OIDC claims to an enabled local account."""

        if not isinstance(user_info, Mapping):
            raise OIDCAuthenticationError("Failed to retrieve user info from OIDC provider.")

        claims = cast(Mapping[str, object], user_info)
        issuer = claims.get("iss")
        if not isinstance(issuer, str) or issuer != self.issuer:
            raise OIDCAuthenticationError("Invalid issuer in OIDC identity.")
        subject = claims.get("sub")
        if not isinstance(subject, str) or not subject.strip():
            raise OIDCAuthenticationError("Invalid subject in user info from OIDC provider.")

        user = self.user_service.get_by_oidc(self.issuer, subject)
        preferred_username = claims.get("preferred_username")
        if (
            user is None
            and allow_first_link
            and self.initial_admin_username is not None
            and preferred_username == self.initial_admin_username
        ):
            user = self.user_service.link_first_oidc_admin_identity(
                self.initial_admin_username,
                self.issuer,
                subject,
            )
        if user is None:
            raise OIDCAuthenticationError("No account found for the OIDC identity.")
        if not user.enabled:
            raise OIDCAuthenticationError(
                "The account associated with the OIDC subject is not enabled.",
            )

        return UnifiedUser.from_db_user(user)
