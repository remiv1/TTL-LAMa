"""Reusable user persistence and logical deletion."""
from __future__ import annotations

from sqlalchemy import select, update
from sqlalchemy.orm import Session
from sqlalchemy.sql.elements import ColumnElement

from api.common.db_objects.users import User
from api.common.db_objects.devices import Device
from api.common.db_objects.leases import Lease
from api.common.db_objects.profiles import ProfileUser
from api.common.db_objects.sessions import Session as UserSession
from api.common.db_objects.credentials import Credentials
from api.common.other_objects import AuthMethod
from .base import ConflictError, Repository
from .leases import LeaseRepository, utcnow


class UserRepository(Repository[User]):
    """Manage users while preserving dependent history."""

    def __init__(self, session: Session) -> None:
        super().__init__(session, User)

    def by_username(self, username: str, *, refresh: bool = False) -> User | None:
        """Resolve the same identity for authentication and administration."""
        return self.session.scalar(
            select(User).where(User.username == username).execution_options(populate_existing=refresh)
        )

    def create(self, *, username: str, email: str | None = None,
               enabled: bool = True, is_admin: bool = False,
               password_hash: str | None = None) -> User:
        """Create an identity with optional already-hashed internal credentials."""
        user = User(username=username, email=email, enabled=enabled, is_admin=is_admin)
        if password_hash is not None:
            user.credentials.append(Credentials(
                auth_method=AuthMethod.INTERNAL.value, hash_password=password_hash
            ))
        return self.add(user)

    def set_password(self, user: User, password_hash: str) -> None:
        """Replace internal credentials and invalidate previously issued sessions."""
        credentials = [item for item in user.credentials
                       if item.auth_method == AuthMethod.INTERNAL.value]
        if len(credentials) > 1:
            raise ConflictError("Multiple internal credentials exist for this user")
        if credentials:
            credentials[0].hash_password = password_hash
        else:
            user.credentials.append(Credentials(
                auth_method=AuthMethod.INTERNAL.value, hash_password=password_hash
            ))
        self.revoke_sessions(user)

    def set_admin(self, user: User, is_admin: bool) -> None:
        """Invalidate sessions when administrative privileges change."""
        if user.is_admin != is_admin:
            user.is_admin = is_admin
            self.revoke_sessions(user)

    def find(self, *, device: int | None = None, lease: int | None = None,
             profile: int | None = None) -> list[User]:
        """Combine device, lease and active profile-assignment filters."""
        conditions: list[ColumnElement[bool]] = []
        if device is not None:
            conditions.append(User.id.in_(select(Device.user_id).where(Device.id == device)))
        if lease is not None:
            conditions.append(User.id.in_(select(Lease.user_id).where(Lease.id == lease)))
        if profile is not None:
            conditions.append(User.id.in_(select(ProfileUser.user_id).where(
                ProfileUser.profile_id == profile, ProfileUser.revoked_at.is_(None)
            )))
        return self.list(*conditions)

    def revoke_sessions(self, user: User) -> None:
        """Invalidate sessions after credential or privilege changes."""
        self.session.execute(update(UserSession).where(
            UserSession.user_id == str(user.id), UserSession.revoked_at.is_(None)
        ).values(revoked_at=utcnow()))

    def disable(self, user: User) -> User:
        """Disable a user and revoke all dependent access."""
        user.enabled = False
        self.revoke_sessions(user)
        LeaseRepository(self.session).revoke_matching(Lease.user_id == str(user.id))
        for model in (Device, ProfileUser):
            self.session.execute(update(model).where(
                model.user_id == str(user.id), model.revoked_at.is_(None)
            ).values(revoked_at=utcnow()))
        return user
