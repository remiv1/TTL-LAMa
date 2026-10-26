"""Tests for the UserService class."""

import pytest

from auth.services.user import UserService
from api.common.db_objects import User

@pytest.mark.parametrize(
    ("subject", "expected_username"),
    [
        ("known-subject", "alice"),
        ("unknown-subject", None)
    ],
    ids=["identity-linked", "identity-unknown"]
)
def test_get_by_oidc_returns_expected_user(
    user_service: UserService,
    user_with_oidc_identity: User,  # pylint: disable=W0613
    subject: str,
    expected_username: str | None,
):
    """Test that get_by_oidc returns the expected user based on the subject."""
    result = user_service.get_by_oidc("http://dex:5556/dex", subject)

    assert (result.username if result is not None else None) == expected_username
    if result is not None:
        assert result.username == expected_username
