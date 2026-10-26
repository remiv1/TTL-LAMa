"""User fixture for TTL-LAMa tests."""
from __future__ import annotations

import pytest
from flask import Flask

from auth.services.user import UserService

@pytest.fixture
def user_service(app: Flask) -> UserService:
    """Provide a UserService instance for tests."""
    database = app.extensions["database_config"]
    return UserService(database.session())

@pytest.fixture
def user_with_oidc_identity(user_service: UserService): # pylint: disable=W0621
    """Provide a user with an OIDC identity for tests."""
    from api.common.db_objects import User, UserOIDCUser  # pylint: disable=C0415
    oidc_user = UserOIDCUser(
        subject="known-subject",
        issuer="http://dex:5556/dex"
    )
    user = User(
        username="alice",
        email="alice@example.com",
        oidc_users=[oidc_user],
        enabled=True,
        is_admin=False,
        last_login=None,
    )
    return user_service.upsert_user(user)
