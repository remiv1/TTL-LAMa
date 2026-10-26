"""Tests for the OIDC authentication backend."""

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

    def authorize_access_token(self) -> dict[str, object]:
        """Simulate the retrieval of an access token with user info."""
        return cast(dict[str, object], self.token)

    def authorize_redirect(self, redirect_uri: str) -> Response:
        """Simulate the authorization redirect."""
        self.redirect_uri = redirect_uri
        return self.redirect_response


class FakeUserService:   # pylint: disable=R0903
    """Fake user service for testing purposes."""

    def __init__(self, user: User | None) -> None:
        self.user = user
        self.lookup: tuple[str, str] | None = None

    def get_by_oidc(self, issuer: str, subject: str) -> User | None:
        """Simulate retrieving a user by their OIDC issuer and subject."""
        self.lookup = (issuer, subject)
        return self.user

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
