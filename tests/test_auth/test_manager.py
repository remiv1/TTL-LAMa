"""Tests for the authentication manager."""

from typing import cast

from auth.backends import AuthBackend
from auth.manager import AuthManager
from auth.models import AuthenticationResult, UnifiedUser
from auth.services import SessionService, UserService
from api.common.db_objects import User


class FakeBackend(AuthBackend):
    """A fake authentication backend for testing purposes."""
    def __init__(
            self,
            user: UnifiedUser,
            authenticated_user: UnifiedUser | None = None) -> None:
        self.user = user
        self.authenticated_user = authenticated_user

    def authenticate(
        self,
        credentials: dict[str, object] | None = None,
    ) -> UnifiedUser | None:
        return self.authenticated_user

    def complete_login(self) -> UnifiedUser:
        return self.user

class FakeSessionService:   # pylint: disable=R0903
    """A fake session service for testing purposes."""
    def __init__(self) -> None:
        self.created_for: str | None = None
        self.user_id_by_token: dict[str, str] = {}
        self.revoked_tokens: str | None = None

    def create(self, user_id: str) -> str:
        """Create a session for the given user ID and return the session token."""
        self.created_for = user_id
        return "session-token"

    def get_user_id(self, token: str | None) -> str | None:
        """Get the user ID associated with the given session token."""
        return self.user_id_by_token.get(token) if token else None

    def revoke(self, token: str | None) -> None:
        """Revoke the session associated with the given token."""
        self.revoked_tokens = token

class FakeUserService:  # pylint: disable=R0903
    """A fake user service for testing purposes."""
    def __init__(self, user: User) -> None:
        self.user = user
        self.requested_id: str | None = None

    def get_by_id(self, user_id: str) -> User:
        """Get the user by ID."""
        self.requested_id = user_id
        if str(self.user.id) != user_id:
            raise ValueError("User not found")
        return self.user

def test_complete_login_creates_session_and_returns_result() -> None:
    """Test that completing login creates a session and returns the authentication result."""
    user = UnifiedUser(
        id="local-user-id",
        username="alice",
        is_admin=False,
    )
    backend = FakeBackend(user)
    sessions = FakeSessionService()
    manager = AuthManager(
        backend=backend,
        session_service=cast(SessionService, sessions),
        user_service=cast(UserService, object()),
    )

    result = manager.complete_login()

    assert result == AuthenticationResult(
        user=user,
        session_token="session-token",
    )
    assert sessions.created_for == user.id

def test_authenticate_returns_none_without_creating_session() -> None:
    """Test that authenticate returns None and does not create a session."""
    user = UnifiedUser(
        id="local-user-id",
        username="alice",
        is_admin=False,
    )
    backend = FakeBackend(user)
    sessions = FakeSessionService()
    manager = AuthManager(
        backend=backend,
        session_service=cast(SessionService, sessions),
        user_service=cast(UserService, object()),
    )

    result = manager.authenticate(
        {"username": "alice", "password": "wrong-password"}
    )

    assert result is None
    assert sessions.created_for is None

def test_authenticate_creates_session_and_returns_result() -> None:
    """Test that authenticate creates a session and returns the authentication result."""
    user = UnifiedUser(
        id="local-user-id",
        username="alice",
        is_admin=False,
    )
    backend = FakeBackend(user, authenticated_user=user)
    sessions = FakeSessionService()
    manager = AuthManager(
        backend=backend,
        session_service=cast(SessionService, sessions),
        user_service=cast(UserService, object()),
    )

    result = manager.authenticate(
        {"username": "alice", "password": "correct-password"}
    )

    assert result == AuthenticationResult(
        user=user,
        session_token="session-token",
    )
    assert sessions.created_for == user.id

def test_get_current_user_returns_active_local_user() -> None:
    """Test that get_current_user returns the active local user."""
    local_user = User(
        id="local-user-id",
        username="alice",
        email="alice@example.com",
        enabled=True,
        is_admin=True,
    )
    sessions = FakeSessionService()
    sessions.user_id_by_token["session-token"] = "local-user-id"
    users = FakeUserService(local_user)
    manager = AuthManager(
        backend=cast(AuthBackend, object()),
        session_service=cast(SessionService, sessions),
        user_service=cast(UserService, users),
    )

    result = manager.get_current_user("session-token")

    assert result == UnifiedUser(
        id="local-user-id",
        username="alice",
        is_admin=True,
        email="alice@example.com",
    )
    assert users.requested_id == "local-user-id"

def test_get_current_user_returns_none_for_unknown_token() -> None:
    """Test that get_current_user returns None for an unknown session token."""
    sessions = FakeSessionService()
    users = cast(UserService, object())
    manager = AuthManager(
        backend=cast(AuthBackend, object()),
        session_service=cast(SessionService, sessions),
        user_service=users,
    )

    result = manager.get_current_user("unknown-token")

    assert result is None

def test_get_current_user_returns_none_for_disabled_local_user() -> None:
    """Test that get_current_user returns None for a disabled local user."""
    local_user = User(
        id="local-user-id",
        username="alice",
        email="alice@example.com",
        enabled=False,
        is_admin=True,
    )
    sessions = FakeSessionService()
    sessions.user_id_by_token["session-token"] = "local-user-id"
    users = FakeUserService(local_user)
    manager = AuthManager(
        backend=cast(AuthBackend, object()),
        session_service=cast(SessionService, sessions),
        user_service=cast(UserService, users),
    )

    result = manager.get_current_user("session-token")

    assert result is None
    assert users.requested_id == "local-user-id"

def test_logout_revokes_session_token() -> None:
    """Test that logout revokes the session token."""
    sessions = FakeSessionService()
    manager = AuthManager(
        backend=cast(AuthBackend, object()),
        session_service=cast(SessionService, sessions),
        user_service=cast(UserService, object()),
    )

    manager.logout("session-token")

    assert sessions.revoked_tokens == "session-token"
