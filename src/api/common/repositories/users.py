"""Reusable user persistence and logical deletion.

.. classes::
    - `UserRepository`: Manages user persistence, logical deletion, and related access control.

.. module_author:: Rémi Verschuur <rverschuur@audit-io.fr>
.. version:: 1.0.0
"""
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
    """Manage users while preserving dependent history.
    
    :param session: The SQLAlchemy session to use for database operations.
    :type session: Session
    """

    def __init__(self, session: Session) -> None:
        super().__init__(session, User)

    def by_username(self, username: str, *, refresh: bool = False) -> User | None:
        """Resolve the same identity for authentication and administration.
        
        :param username: The username of the user to retrieve.
        :type username: str
        :param refresh: Whether to refresh the object from the database.
        :type refresh: bool
        :return: The user with the given username, or None if not found.
        :rtype: User | None
        """
        return self.session.scalar(
            select(User)
            .where(User.username == username)
            .execution_options(populate_existing=refresh)
        )

    def create( # pylint: disable=R0913
        self,
        *,
        username: str,
        email: str | None = None,
        enabled: bool = True,
        is_admin: bool = False,
        password_hash: str | None = None
    ) -> User:
        """Create an identity with optional already-hashed internal credentials.
        
        :param username: The username of the new user.
        :type username: str
        :param email: The email of the new user.
        :type email: str | None
        :param enabled: Whether the user is enabled.
        :type enabled: bool
        :param is_admin: Whether the user has administrative privileges.
        :type is_admin: bool
        :param password_hash: The already-hashed password for the user.
        :type password_hash: str | None
        :return: The newly created user.
        :rtype: User
        """
        user = User(username=username, email=email, enabled=enabled, is_admin=is_admin)
        if password_hash is not None:
            user.credentials.append(Credentials(
                auth_method=AuthMethod.INTERNAL.value, hash_password=password_hash
            ))
        return self.add(user)

    def set_password(self, user: User, password_hash: str) -> None:
        """Replace internal credentials and invalidate previously issued sessions.
        
        :param user: The user whose password is being set.
        :type user: User
        :param password_hash: The new hashed password for the user.
        :type password_hash: str
        """
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

    def set_last_login(self, user: User) -> None:
        """Record the current UTC time as the user's last successful login.

        :param user: The user whose login time is being recorded.
        :type user: User
        """
        user.last_login = utcnow()

    def set_admin(self, user: User, is_admin: bool) -> None:
        """Invalidate sessions when administrative privileges change.
        
        :param user: The user whose administrative privileges are being changed.
        :type user: User
        :param is_admin: The new administrative status for the user.
        :type is_admin: bool
        """
        if user.is_admin != is_admin:
            user.is_admin = is_admin
            self.revoke_sessions(user)

    def find(self, *, device: int | None = None, lease: int | None = None,
             profile: int | None = None) -> list[User]:
        """Combine device, lease and active profile-assignment filters.
        
        :param device: The ID of the device to filter by.
        :type device: int | None
        :param lease: The ID of the lease to filter by.
        :type lease: int | None
        :param profile: The ID of the profile to filter by.
        :type profile: int | None
        :return: A list of users matching the specified filters.
        :rtype: list[User]
        """
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
        """Invalidate sessions after credential or privilege changes.
        
        :param user: The user whose sessions are being revoked.
        :type user: User
        """
        self.session.execute(update(UserSession).where(
            UserSession.user_id == str(user.id), UserSession.revoked_at.is_(None)
        ).values(revoked_at=utcnow()))

    def disable(self, user: User) -> User:
        """Disable a user and revoke all dependent access.
        
        :param user: The user to disable.
        :type user: User
        :return: The disabled user.
        :rtype: User
        """
        user.enabled = False
        self.revoke_sessions(user)
        LeaseRepository(self.session).revoke_matching(Lease.user_id == str(user.id))
        for model in (Device, ProfileUser):
            self.session.execute(update(model).where(
                model.user_id == str(user.id), model.revoked_at.is_(None)
            ).values(revoked_at=utcnow()))
        return user
