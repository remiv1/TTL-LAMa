"""Tests for the session service."""
import hashlib
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from api.common.db_objects import User
from api.common.db_objects.sessions import Session as UserSession
from auth.services import SessionService, UserService

def test_get_user_id_returns_id_for_valid_token(
        user_service: UserService,
        user_with_oidc_identity: User,
) -> None:
    """Test that get_user_id returns the correct user ID for a valid token."""
    session_service = SessionService(
        db_session=user_service.db_session,
        lifetime=timedelta(minutes=5),
    )
    token = session_service.create(user_with_oidc_identity.id)

    assert session_service.get_user_id(token) == str(user_with_oidc_identity.id)

    stored_session = user_service.db_session.scalar(
        select(UserSession).where(
            UserSession.user_id == str(user_with_oidc_identity.id)
        )
    )
    assert stored_session is not None
    assert stored_session.token_hash != token

@pytest.mark.parametrize(
    "token",
    [None, "", "unknown-token"],
    ids=["missing", "empty", "unknown"],
)
def test_get_user_id_returns_none_for_invalid_token(
    user_service: UserService,
    token: str | None,
) -> None:
    """Test that get_user_id returns None for invalid tokens."""
    session_service = SessionService(
        db_session=user_service.db_session,
        lifetime=timedelta(minutes=5),
    )
    assert session_service.get_user_id(token) is None

def test_get_user_id_returns_none_for_expired_token(
    user_service: UserService,
    user_with_oidc_identity: User,
) -> None:
    """Test that get_user_id returns None for expired tokens."""
    session_service = SessionService(
        db_session=user_service.db_session,
        lifetime=timedelta(minutes=5),  # Positive lifetime to create a valid session
    )
    token = session_service.create(user_with_oidc_identity.id)

    token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
    stored_session = user_service.db_session.scalar(
        select(UserSession).where(UserSession.token_hash == token_hash)
    )
    assert stored_session is not None

    stored_session.expires_at = (
        datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(seconds=1)
    )
    user_service.db_session.commit()

    assert session_service.get_user_id(token) is None

@pytest.mark.parametrize("lifetime", [timedelta(0), timedelta(seconds=-1)])
def test_session_service_rejects_non_positive_lifetime(
    user_service: UserService,
    lifetime: timedelta,
) -> None:
    """Test that the session service rejects non-positive lifetimes."""
    with pytest.raises(ValueError):
        SessionService(user_service.db_session, lifetime)

def test_revoke_invalidates_session_token(
    user_service: UserService,
    user_with_oidc_identity: User,
) -> None:
    """Test that revoking a session makes its token unusable."""
    session_service = SessionService(
        db_session=user_service.db_session,
        lifetime=timedelta(minutes=5),
    )
    token = session_service.create(user_with_oidc_identity.id)

    assert session_service.get_user_id(token) == str(user_with_oidc_identity.id)

    session_service.revoke(token)

    assert session_service.get_user_id(token) is None

    token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
    stored_session = user_service.db_session.scalar(
        select(UserSession).where(UserSession.token_hash == token_hash)
    )
    assert stored_session is not None
    assert stored_session.revoked_at is not None

def test_revoke_is_idempotent(
        user_service: UserService,
        user_with_oidc_identity: User,
) -> None:
    """Test that revoking a session multiple times is idempotent."""
    session_service = SessionService(
        db_session=user_service.db_session,
        lifetime=timedelta(minutes=5),
    )
    token = session_service.create(user_with_oidc_identity.id)

    assert session_service.get_user_id(token) == str(user_with_oidc_identity.id)

    session_service.revoke(token)
    token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
    stmt = select(UserSession).where(UserSession.token_hash == token_hash)
    stored_session = user_service.db_session.scalar(stmt)

    assert stored_session is not None

    first_revocation = stored_session.revoked_at
    session_service.revoke(token)  # Revoke again to test idempotency

    user_service.db_session.refresh(stored_session)
    assert stored_session.revoked_at == first_revocation

    assert session_service.get_user_id(token) is None
