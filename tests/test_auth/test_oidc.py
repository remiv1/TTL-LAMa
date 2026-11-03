"""Tests for the OIDC authentication backend."""

from collections.abc import Mapping
from typing import cast
import pytest

from flask import Response
from authlib.integrations.flask_client.apps import FlaskOAuth2App

from api.common.db_objects import User
from auth.backends.oidc import OIDCAuthBackend
from auth.models import OIDCParams, UnifiedUser
from auth.services import UserService
from auth.exceptions import AccountNotFoundError, OIDCAuthenticationError


class FakeOIDCClient:   # pylint: disable=R0903
    """Fake OIDC client for testing purposes."""
    def __init__(self, token: dict[str, object] | None = None) -> None:
        self.token = (
            token
            if token is not None
            else {"userinfo": {"sub": "known-subject"}}
        )
        self.redirect_uri: str | None = None
        self.redirect_response = Response(status=302)
        self.metadata: dict[str, object] = {
            "device_authorization_endpoint": "https://idp.example/device",
            "token_endpoint": "https://idp.example/token",
        }
        self.device_user_info: Mapping[str, object] = {"sub": "known-subject"}

    def authorize_access_token(self) -> dict[str, object]:
        """Simulate the retrieval of an access token with user info."""
        return cast(dict[str, object], self.token)

    def authorize_redirect(self, redirect_uri: str) -> Response:
        """Simulate the authorization redirect."""
        self.redirect_uri = redirect_uri
        return self.redirect_response

    def load_server_metadata(self) -> dict[str, object]:
        """Return fake provider metadata for Device Authorization tests."""
        return self.metadata

    def userinfo(self, **_kwargs: object) -> Mapping[str, object]:
        """Return fake user information for a validated provider token."""
        return self.device_user_info

    def parse_id_token(
        self,
        _token: dict[str, object],
        nonce: str | None,
    ) -> Mapping[str, object] | None:
        """Return claims after simulating Authlib ID token validation."""
        assert nonce is None
        return self.device_user_info


class FakeProviderResponse:  # pylint: disable=R0903
    """Minimal HTTP response for OIDC provider endpoint tests."""

    def __init__(self, status_code: int, payload: dict[str, object]) -> None:
        self.status_code = status_code
        self.payload = payload

    def json(self) -> dict[str, object]:
        """Return the configured JSON payload."""
        return self.payload


class FakeUserService:   # pylint: disable=R0903
    """Fake user service for testing purposes."""

    def __init__(self, user: User | None) -> None:
        self.user = user
        self.lookup: tuple[str, str] | None = None
        self.first_link_user: User | None = None
        self.first_link_call: tuple[str, str, str] | None = None

    def get_by_oidc(self, issuer: str, subject: str) -> User | None:
        """Simulate retrieving a user by their OIDC issuer and subject."""
        self.lookup = (issuer, subject)
        return self.user

    def link_first_oidc_admin_identity(
        self,
        username: str,
        issuer: str,
        subject: str,
    ) -> User | None:
        """Record and simulate the guarded first-admin identity link."""
        self.first_link_call = (username, issuer, subject)
        return self.first_link_user

def test_complete_login_returns_linked_local_user() -> None:
    """Test that completing login returns the linked local user."""
    local_user = User(
        id="local-user-id",
        username="alice",
        email="alice@example.com",
        enabled=True,
        is_admin=True,
    )
    user_service = FakeUserService(local_user)
    oidc_params = OIDCParams(
        oidc_client=cast(FlaskOAuth2App, FakeOIDCClient()),
        issuer="http://dex:5556/dex",
        redirect_uri="http://localhost/auth/callback",
    )

    backend = OIDCAuthBackend(
        user_service=cast(UserService, user_service),
        oidc_params=oidc_params,
    )
    result = backend.complete_login()

    assert result == UnifiedUser(
        id="local-user-id",
        username="alice",
        is_admin=True,
        email="alice@example.com",
    )
    assert user_service.lookup == ("http://dex:5556/dex", "known-subject")

def test_complete_login_rejects_unknown_identity() -> None:
    """Test that completing login rejects an unknown identity."""
    user_service = FakeUserService(None)
    oidc_params = OIDCParams(
        oidc_client=cast(FlaskOAuth2App, FakeOIDCClient()),
        issuer="http://dex:5556/dex",
        redirect_uri="http://localhost/auth/callback",
    )
    backend = OIDCAuthBackend(
        user_service=cast(UserService, user_service),
        oidc_params=oidc_params,
    )

    with pytest.raises(AccountNotFoundError):
        backend.complete_login()

    assert user_service.lookup == ("http://dex:5556/dex", "known-subject")


def test_complete_login_links_first_admin_identity_on_matching_username() -> None:
    """Link an unknown OIDC subject only for the configured preferred username."""
    admin = User(
        id="local-admin-id",
        username="admin",
        enabled=True,
        is_admin=True,
    )
    user_service = FakeUserService(None)
    user_service.first_link_user = admin
    oidc_client = FakeOIDCClient({
        "userinfo": {
            "sub": "first-subject",
            "preferred_username": "admin",
        },
    })
    backend = OIDCAuthBackend(
        cast(UserService, user_service),
        OIDCParams(
            oidc_client=cast(FlaskOAuth2App, oidc_client),
            issuer="http://dex:5556/dex",
            redirect_uri="http://localhost/auth/callback",
        ),
        initial_admin_username="admin",
    )

    result = backend.complete_login()

    assert result.username == "admin"
    assert user_service.first_link_call == (
        "admin",
        "http://dex:5556/dex",
        "first-subject",
    )


def test_complete_login_does_not_link_first_identity_for_different_username() -> None:
    """Reject the first identity when its preferred username differs from admin."""
    user_service = FakeUserService(None)
    user_service.first_link_user = User(
        id="local-admin-id",
        username="admin",
        enabled=True,
        is_admin=True,
    )
    oidc_client = FakeOIDCClient({
        "userinfo": {
            "sub": "other-subject",
            "preferred_username": "alice",
        },
    })
    backend = OIDCAuthBackend(
        cast(UserService, user_service),
        OIDCParams(
            oidc_client=cast(FlaskOAuth2App, oidc_client),
            issuer="http://dex:5556/dex",
            redirect_uri="http://localhost/auth/callback",
        ),
        initial_admin_username="admin",
    )

    with pytest.raises(AccountNotFoundError):
        backend.complete_login()

    assert user_service.first_link_call is None

def test_complete_login_rejects_disabled_user() -> None:
    """Test that completing login rejects a disabled user."""
    local_user = User(
        id="local_user_id",
        username="alice",
        email="alice@example.com",
        enabled=False,
        is_admin=False,
    )
    user_service = FakeUserService(local_user)
    oidc_params = OIDCParams(
        oidc_client=cast(FlaskOAuth2App, FakeOIDCClient()),
        issuer="http://dex:5556/dex",
        redirect_uri="http://localhost/auth/callback",
    )
    backend = OIDCAuthBackend(
        user_service=cast(UserService, user_service),
        oidc_params=oidc_params,
    )

    with pytest.raises(OIDCAuthenticationError):
        backend.complete_login()

    assert user_service.lookup == ("http://dex:5556/dex", "known-subject")

@pytest.mark.parametrize(
    "token",
    [
        {},
        {"userinfo": None},
        {"userinfo": {}},
        {"userinfo": {"sub": ""}},
    ],
    ids=["userinfo-absent", "userinfo-null", "subject-absent", "subject-empty"],
)
def test_complete_login_rejects_invalid_user_info(
    token: dict[str, object],
) -> None:
    """Test that completing login rejects invalid user info."""
    user_service = FakeUserService(None)
    oidc_params = OIDCParams(
        oidc_client=cast(FlaskOAuth2App, FakeOIDCClient(token)),
        issuer="http://dex:5556/dex",
        redirect_uri="http://localhost/auth/callback",
    )
    backend = OIDCAuthBackend(
        user_service=cast(UserService, user_service),
        oidc_params=oidc_params,
    )

    with pytest.raises(OIDCAuthenticationError):
        backend.complete_login()

    assert user_service.lookup is None

def test_begin_login_redirects_to_oidc_provider() -> None:
    """Test that beginning login redirects to the OIDC provider."""
    oidc_client = FakeOIDCClient()
    redirect_uri = "http://localhost/auth/callback"
    oidc_params = OIDCParams(
        oidc_client=cast(FlaskOAuth2App, oidc_client),
        issuer="http://dex:5556/dex",
        redirect_uri=redirect_uri,
    )
    backend = OIDCAuthBackend(
        user_service=cast(UserService, FakeUserService(None)),
        oidc_params=oidc_params,
    )

    response = backend.begin_login()

    assert response is oidc_client.redirect_response
    assert oidc_client.redirect_uri == redirect_uri


def test_begin_device_authorization_returns_only_provider_device_fields(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Device authorization start validates the provider's public response fields."""
    from auth.backends import oidc as oidc_module # pylint: disable=C0415

    response = FakeProviderResponse(
        200,
        {
            "device_code": "private-device-code",
            "user_code": "ABCD-EFGH",
            "verification_uri": "https://idp.example/device",
            "verification_uri_complete": "https://idp.example/device?user_code=ABCD-EFGH",
            "expires_in": 300,
            "interval": 5,
        },
    )
    def provider_post(*_args: object, **kwargs: object) -> FakeProviderResponse:
        assert kwargs.get("data") == {
            "client_id": "cli-client",
            "client_secret": "client-secret",
            "scope": "openid profile",
        }
        assert "auth" not in kwargs
        return response

    monkeypatch.setattr(oidc_module, "post", provider_post)
    backend = OIDCAuthBackend(
        cast(UserService, FakeUserService(None)),
        OIDCParams(
            oidc_client=cast(FlaskOAuth2App, FakeOIDCClient()),
            issuer="https://idp.example",
            redirect_uri="http://localhost/auth/callback",
        ),
    )

    result = backend.begin_device_authorization("cli-client", "client-secret")

    assert result["device_code"] == "private-device-code"
    assert result["user_code"] == "ABCD-EFGH"
    assert result["expires_in"] == 300
    assert result["interval"] == 5


@pytest.mark.parametrize(
    ("provider_error", "expected_status"),
    [
        ("authorization_pending", "pending"),
        ("slow_down", "slow_down"),
        ("access_denied", "denied"),
        ("expired_token", "expired"),
    ],
)
def test_poll_device_authorization_maps_provider_status(
    monkeypatch: pytest.MonkeyPatch,
    provider_error: str,
    expected_status: str,
) -> None:
    """Standard device grant errors become non-sensitive polling states."""
    from auth.backends import oidc as oidc_module # pylint: disable=C0415

    def provider_post(*_args: object, **_kwargs: object) -> FakeProviderResponse:
        return FakeProviderResponse(400, {"error": provider_error})

    monkeypatch.setattr(oidc_module, "post", provider_post)
    backend = OIDCAuthBackend(
        cast(UserService, FakeUserService(None)),
        OIDCParams(
            oidc_client=cast(FlaskOAuth2App, FakeOIDCClient()),
            issuer="https://idp.example",
            redirect_uri="http://localhost/auth/callback",
        ),
    )

    assert backend.poll_device_authorization(
        "private-device-code",
        "cli-client",
        "client-secret",
    ) == {"status": expected_status}


def test_poll_device_authorization_resolves_linked_user(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An approved access token is resolved through the configured userinfo endpoint."""
    from auth.backends import oidc as oidc_module # pylint: disable=C0415

    local_user = User(
        id="local-user-id",
        username="alice",
        email="alice@example.com",
        enabled=True,
        is_admin=False,
    )
    user_service = FakeUserService(local_user)
    oidc_client = FakeOIDCClient()
    oidc_module_response = FakeProviderResponse(200, {"access_token": "provider-token"})
    def provider_post(*_args: object, **_kwargs: object) -> FakeProviderResponse:
        return oidc_module_response

    monkeypatch.setattr(oidc_module, "post", provider_post)
    backend = OIDCAuthBackend(
        cast(UserService, user_service),
        OIDCParams(
            oidc_client=cast(FlaskOAuth2App, oidc_client),
            issuer="https://idp.example",
            redirect_uri="http://localhost/auth/callback",
        ),
    )

    result = backend.poll_device_authorization(
        "private-device-code",
        "cli-client",
        "client-secret",
    )

    assert result == {
        "status": "complete",
        "user": UnifiedUser(
            id="local-user-id",
            username="alice",
            is_admin=False,
            email="alice@example.com",
        ),
    }
    assert user_service.lookup == ("https://idp.example", "known-subject")


@pytest.mark.parametrize(
    ("preferred_username", "expected_link"),
    [("admin", True), ("alice", False)],
)
def test_poll_device_authorization_links_first_admin_only_for_matching_username(
    monkeypatch: pytest.MonkeyPatch,
    preferred_username: str,
    expected_link: bool,
) -> None:
    """Only the configured admin username can claim the first device identity."""
    from auth.backends import oidc as oidc_module # pylint: disable=C0415

    admin = User(
        id="local-admin-id",
        username="admin",
        enabled=True,
        is_admin=True,
    )
    user_service = FakeUserService(None)
    user_service.first_link_user = admin
    oidc_client = FakeOIDCClient()
    oidc_client.device_user_info = {
        "sub": "first-subject",
        "preferred_username": preferred_username,
    }

    def provider_post(*_args: object, **_kwargs: object) -> FakeProviderResponse:
        return FakeProviderResponse(200, {"access_token": "provider-token"})

    monkeypatch.setattr(oidc_module, "post", provider_post)
    backend = OIDCAuthBackend(
        cast(UserService, user_service),
        OIDCParams(
            oidc_client=cast(FlaskOAuth2App, oidc_client),
            issuer="https://idp.example",
            redirect_uri="http://localhost/auth/callback",
        ),
        initial_admin_username="admin",
    )

    if expected_link:
        result = backend.poll_device_authorization(
            "private-device-code",
            "cli-client",
            "client-secret",
        )
        assert result == {"status": "complete", "user": UnifiedUser.from_db_user(admin)}
        assert user_service.first_link_call == (
            "admin",
            "https://idp.example",
            "first-subject",
        )
    else:
        with pytest.raises(AccountNotFoundError):
            backend.poll_device_authorization(
                "private-device-code",
                "cli-client",
                "client-secret",
            )
        assert user_service.first_link_call is None
