"""Tests du backend d’authentification interne."""

from types import SimpleNamespace
from typing import cast

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError

from api.common.other_objects import AuthMethod
from auth.backends.internal import InternalAuthBackend
from auth.models import UnifiedUser
from auth.services import UserService


class FakeUserService:
    """Minimal users service for testing the internal backend."""

    def __init__(self, user: SimpleNamespace) -> None:
        self.user = user

    def get_by_username(self, username: str) -> SimpleNamespace | None:
        """Returns the user with the given username, or None if not found."""
        if self.user.username == username:
            return self.user
        return None


class FakePasswordHasher:
    """Test password hasher that records verification arguments."""

    def __init__(self, error: Exception | None = None) -> None:
        self.error = error
        self.verified: tuple[str, str] | None = None

    def verify(self, hash_value: str, password: str) -> bool:
        """Verify the given password against the hash."""
        self.verified = (hash_value, password)
        if self.error is not None:
            raise self.error
        return True


def _make_backend(
    error: Exception | None = None,
) -> tuple[InternalAuthBackend, FakePasswordHasher]:
    user = SimpleNamespace(
        id="user-id",
        username="alice",
        email="alice@example.com",
        enabled=True,
        is_admin=False,
        credentials=[
            SimpleNamespace(
                auth_method=AuthMethod.INTERNAL.value,
                hash_password="argon2-hash",
            ),
        ],
    )
    hasher = FakePasswordHasher(error)
    backend = InternalAuthBackend(
        cast(UserService, FakeUserService(user)),
        cast(PasswordHasher, hasher),
    )
    return backend, hasher


def test_authenticate_uses_injected_password_hasher() -> None:
    """Uses the injected hasher and returns the authenticated user."""
    backend, hasher = _make_backend()

    user = backend.authenticate({"username": "alice", "password": "correct"})

    assert user == UnifiedUser(
        id="user-id",
        username="alice",
        is_admin=False,
        email="alice@example.com",
    )
    assert hasher.verified == ("argon2-hash", "correct")


def test_authenticate_rejects_password_verification_errors() -> None:
    """Rejects authentication in case of Argon2 verification error."""
    backend, hasher = _make_backend(VerifyMismatchError("mismatch"))

    user = backend.authenticate({"username": "alice", "password": "wrong"})

    assert user is None
    assert hasher.verified == ("argon2-hash", "wrong")
