"""Test cases for authentication decorators."""

from flask import Flask

from auth.decorators import get_authenticated_user, require_authenticated_user
from auth.models import UnifiedUser


class FakeAuthManager:  # pylint: disable=R0903
    """Fake orchestration manager simulated for testing decorators."""

    def __init__(self) -> None:
        self.user = UnifiedUser(
            id="user-1",
            username="alice",
            is_admin=False,
        )
        self.requested_tokens: list[str | None] = []

    def get_current_user(self, session_token: str | None) -> UnifiedUser | None:
        """Get the current authenticated user based on the session token."""
        self.requested_tokens.append(session_token)
        if session_token in {"cookie-token", "bearer-token"}:
            return self.user
        return None


def create_test_app(manager: FakeAuthManager) -> Flask:
    """Create a test Flask app with the given fake auth manager."""
    app = Flask(__name__)
    app.config["AUTH_COOKIE_NAME"] = "ttl-lama_session"
    app.extensions["auth_manager"] = manager

    @app.get("/protected")
    @require_authenticated_user
    def protected() -> str:
        return get_authenticated_user().id

    return app


def test_valid_cookie_authenticates_user() -> None:
    """Test that a valid cookie authenticates the user."""
    manager = FakeAuthManager()
    client = create_test_app(manager).test_client()
    client.set_cookie("ttl-lama_session", "cookie-token")

    response = client.get("/protected")

    assert response.status_code == 200
    assert response.get_data(as_text=True) == "user-1"
    assert manager.requested_tokens == ["cookie-token"]


def test_valid_bearer_token_authenticates_user() -> None:
    """Test that a valid Bearer token authenticates the user."""
    manager = FakeAuthManager()
    client = create_test_app(manager).test_client()

    response = client.get(
        "/protected",
        headers={"Authorization": "Bearer bearer-token"},
    )

    assert response.status_code == 200
    assert response.get_data(as_text=True) == "user-1"
    assert manager.requested_tokens == ["bearer-token"]


def test_missing_token_is_rejected() -> None:
    """Test that a missing token results in rejection with 401."""
    manager = FakeAuthManager()
    client = create_test_app(manager).test_client()

    response = client.get("/protected")

    assert response.status_code == 401
    assert manager.requested_tokens == [None]


def test_invalid_bearer_token_is_rejected() -> None:
    """Test that an invalid Bearer token results in rejection with 401."""
    manager = FakeAuthManager()
    client = create_test_app(manager).test_client()

    response = client.get(
        "/protected",
        headers={"Authorization": "Bearer invalid-token"},
    )

    assert response.status_code == 401
    assert manager.requested_tokens == ["invalid-token"]


def test_malformed_authorization_does_not_fall_back_to_cookie() -> None:
    """Test that a malformed Authorization header does not fall back to cookie authentication."""
    manager = FakeAuthManager()
    client = create_test_app(manager).test_client()
    client.set_cookie("ttl-lama_session", "cookie-token")

    response = client.get(
        "/protected",
        headers={"Authorization": "Basic invalid"},
    )

    assert response.status_code == 401
    assert not manager.requested_tokens
