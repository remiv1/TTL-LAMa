"""Module for managing user-related operations.

.. classes::
    - `UserService` class responsible for managing user-related operations.

.. module_author:: Rémi Verschuur <rverschuur@audit-io.fr>
.. version:: 1.0.0
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session as ORMSession

from api.common.db_objects import User, UserOIDCUser, UserCredentials
from api.common.other_objects import AuthMethod

from ._common import ServiceMixin


if TYPE_CHECKING:
    from ...api.common.db_objects import UserDevice

_WARNING_MESSAGE = "No user has been added, use add_user() first."

class UserService(ServiceMixin):
    """Service class responsible for managing user-related operations.

    :param db_session: The database session used for interacting with the user data.
    :type db_session: ORMSession

    ..author:: Rémi Verschuur <rverschuur@audit-io.fr>
    ..version:: 1.0.0
    """

    def __init__(self, db_session: ORMSession) -> None:
        super().__init__(db_session)
        self._user = None

    def add_user(self, user: User) -> "UserService":
        """Add a user for method chaining.

        :param user: The user object to be added.
        :type user: User

        :return: The `UserService` instance for method chaining.
        :rtype: UserService
        """
        self._user = user
        return self

    def add_credential(self, credential: UserCredentials) -> "UserService":
        """Add a credential for method chaining.

        :param credential: The credential object to be added.
        :type credential: UserCredentials

        :return: The `UserService` instance for method chaining.
        :rtype: UserService
        """
        if not self._user:
            raise ValueError(_WARNING_MESSAGE)
        self._user.credentials.append(credential)
        return self

    def add_device(self, device: UserDevice) -> "UserService":
        """Add a device for method chaining.

        :param device: The device object to be added.
        :type device: UserDevice

        :return: The `UserService` instance for method chaining.
        :rtype: UserService
        """
        if not self._user:
            raise ValueError(_WARNING_MESSAGE)
        self._user.devices.append(device)
        return self

    def create(self) -> User:
        """Create a new user.

        :return: The created user object.
        :rtype: User
        """
        if not self._user:
            raise ValueError(_WARNING_MESSAGE)

        self.db_session.add(self._user)
        self.commit()

        return self._user

    def create_initial_admin(self, username: str, password_hash: str) -> bool:
        """Create the initial admin user.

        :param username: The username of the initial admin.
        :type username: str
        :param password_hash: The hashed password of the initial admin.
        :type password_hash: str

        :return: True if the initial admin was created successfully, False otherwise.
        :rtype: bool
        """
        if self.get_by_username(username) is not None:
            return False
        user = User(
            username=username,
            enabled=True,
            is_admin=True,
        )
        self.add_user(user).add_credential(
            UserCredentials(
                auth_method=AuthMethod.INTERNAL.value,
                hash_password=password_hash,
            )
        ).create()
        return True

    def get_user(self) -> User:
        """Retrieve the currently added user.

        :return: The currently added user object.
        :rtype: User
        """
        if not self._user:
            raise ValueError(_WARNING_MESSAGE)
        return self._user

    def get_by_id(self, user_id: UUID | str) -> User:
        """Retrieve a user by their ID.

        :param user_id: The ID of the user to retrieve.
        :type user_id: UUID | str

        :return: The user object corresponding to the given ID.
        :rtype: User
        """
        stmt = select(User).where(User.id == user_id)
        user = self.db_session.execute(stmt).scalar_one_or_none()
        if not user:
            raise ValueError(f"No user found with ID {user_id}.")
        self._user = user
        return self._user

    def get_by_oidc(self, issuer: str, subject: str) -> User | None:
        """Retrieve a user by their OIDC issuer and subject.

        :param issuer: The OIDC issuer of the user to retrieve.
        :type issuer: str
        :param subject: The OIDC subject of the user to retrieve.
        :type subject: str

        :return: The user object corresponding to the given OIDC credentials, or None if not found.
        :rtype: User | None
        """
        stmt = (
            select(User)
            .join(User.oidc_users)
            .where(
                UserOIDCUser.issuer == issuer,
                UserOIDCUser.subject == subject,
            )
        )
        return self.db_session.execute(stmt).scalar_one_or_none()

    def get_by_username(self, username: str) -> User | None:
        """Retrieve a user by their username.

        :param username: The username of the user to retrieve.
        :type username: str

        :return: The user object corresponding to the given username, or None if not found.
        :rtype: User | None
        """
        stmt = select(User).where(User.username == username)
        return self.db_session.scalars(stmt).one_or_none()

    def delete_user(self, user_id: Optional[UUID | str] = None) -> bool:
        """Delete a user by their ID, or delete the added user if no ID is provided.

        :param user_id: The ID of the user to delete.
        :type user_id: UUID | str

        :return: True if the user was successfully disabled, False otherwise.
        """
        if not user_id and self._user:
            user_id = self._user.id
        if not user_id:
            raise ValueError("User ID must be provided if no user has been added.")
        stmt = select(User).where(User.id == user_id)
        user = self.db_session.execute(stmt).scalar_one_or_none()
        if not user:
            raise ValueError(f"No user found with ID {user_id}.")
        user.enabled = False
        self.db_session.add(user)
        self.commit()
        if self._user and self._user.id == user_id:
            self._user = None
        return self._user is None

    def upsert_user(self, user: User) -> User:
        """Insert a new user or update an existing user.

        :param user: The user object to insert or update.
        :type user: User

        :return: The inserted or updated user object.
        :rtype: User
        """
        stmt = select(User).where(User.username == user.username)
        existing_user = self.db_session.scalar(stmt)
        if existing_user is None:
            persisted_user = user
            self.db_session.add(persisted_user)
        else:
            persisted_user = existing_user
            persisted_user.email = user.email
            persisted_user.enabled = user.enabled
            persisted_user.is_admin = user.is_admin
            persisted_user.last_login = user.last_login

            existing_identities = {
                (identity.issuer, identity.subject)
                for identity in persisted_user.oidc_users
            }
            for identity in user.oidc_users:
                identity_key = (identity.issuer, identity.subject)
                if identity_key not in existing_identities:
                    persisted_user.oidc_users.append(identity)
                    existing_identities.add(identity_key)
        self.commit()

        self._user = persisted_user
        return persisted_user
