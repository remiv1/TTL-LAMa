"""Database objects for users.

.. classes::
    - `User`: Represents a user in the database.
    - `Group`: Represents a group of users in the database.
    - `UserSession`: Represents a session of a user in the database.
    - `UserLoginState`: Represents a user's login attempt state in the database.
    - `AuthRuntimeState`: Represents the authentication runtime state of a user in the database.
    - `UserIdentity`: Represents the identity of a user in the database.
    - `UserPreferences`: Represents the preferences of a user in the database.

.. constant::
    - `_USER_ID`: Description of the unique identifier of the user in the database.

.. author:: Rémi Verschuur <rverschuur@audit-io.fr>
.. version:: 1.0
"""
from __future__ import annotations

from typing import Any
from datetime import datetime, timezone
from uuid import uuid4, UUID

from sqlalchemy import Integer, String, DateTime, Boolean, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from . import Base, TABLE_ARGS, foreign_key_target, table_key

_USER_ID = "Unique identifier of the user"

class User(Base):
    """Database object for a user in the database.

    :param id: The unique identifier of the user.
    :type id: int
    :param username: The username of the user.
    :type username: str
    :param email: The email address of the user.
    :type email: str
    :param hash_password: The hashed password of the user.
    :type hash_password: str
    :param enabled: Indicates whether the user is enabled.
    :type enabled: bool
    :param created_at: Timestamp indicating when the user was created.
    :type created_at: datetime
    :param last_login: Timestamp indicating the last login of the user.
    :type last_login: datetime
    :param groups: List of groups the user belongs to.
    :type groups: list[Group]
    :param sessions: List of user sessions.
    :type sessions: list[UserSession]
    :param preferences: User preferences.
    :type preferences: UserPreferences | None

    .. methods::
        - **`to_dict(without_secrets: bool = True)`** :
        Converts the User object to a dictionary.
        - **`from_dict(data: dict[str, Any], without_secrets: bool = True)`** :
        Creates a User object from a dictionary.

    .. table:: `users`

    .. author:: Rémi Verschuur <rverschuur@audit-io.fr>
    .. version:: 1.0
    """
    __tablename__ = "users"
    __table_args__ = TABLE_ARGS

    id: Mapped[UUID] = mapped_column(
        String(36),
        primary_key=True,
        index=True,
        default=lambda: str(uuid4()),
        comment=_USER_ID,
    )
    username: Mapped[str] = mapped_column(
        String(50),
        unique=True,
        nullable=False,
        comment="Username of the user",
    )
    email: Mapped[str] = mapped_column(
        String(100),
        unique=True,
        nullable=False,
        comment="Email address of the user",
    )
    hash_password: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        comment="Hashed password of the user",
    )
    enabled: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        unique=False,
        comment="Indicates whether the user is enabled",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        unique=False,
        comment="Timestamp indicating when the user was created",
    )
    last_login: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=True,
        unique=False,
        comment="Timestamp indicating the last login of the user",
    )
    groups: Mapped[list["Group"]] = relationship(
        "Group",
        secondary=lambda: Base.metadata.tables[table_key("user_groups")],
        back_populates="users",
    )
    sessions: Mapped[list["UserSession"]] = relationship(
        "UserSession",
        back_populates="user",
    )
    preferences: Mapped["UserPreferences | None"] = relationship(
        cascade="all, delete-orphan",
        single_parent=True,
    )

    def to_dict(self, without_secrets: bool = True) -> dict[str, Any]:
        """Converts the User object to a dictionary.

        :param without_secrets: Whether to exclude sensitive information like the hashed password.
        :type without_secrets: bool
        :return: Dictionary representation of the User object.
        :rtype: dict[str, Any]

        .. note::
            The `without_secrets` parameter controls whether sensitive information like the
            hashed password is included in the dictionary representation. The default value
            is `True`, meaning sensitive information is excluded by default.

            .. code-block:: python

                user = User.from_dict({
                    "id": 1,
                    "username": "john_doe",
                    "email": "john@example.com",
                    "hash_password": "hashed_password",
                })
                print(user.to_dict())
        """
        user_dict = {
            "id": self.id,
            "username": self.username,
            "email": self.email,
        }
        if not without_secrets:
            user_dict["hash_password"] = self.hash_password
        return user_dict

    @classmethod
    def from_dict(cls, data: dict[str, Any], without_secrets: bool = True) -> "User":
        """Creates a User object from a dictionary.

        :param data: Dictionary containing user information.
        :type data: dict[str, Any]
        :param without_secrets: Whether to exclude sensitive information like the hashed password.
        :type without_secrets: bool
        :return: User object created from the dictionary.
        :rtype: User

        .. note::
            The `without_secrets` parameter controls whether sensitive information like the
            hashed password is expected in the input dictionary. The default value is `True`,
            meaning sensitive information is not expected by default.

            .. code-block:: python

                data = {
                    "id": 1,
                    "username": "john_doe",
                    "email": "john@example.com",
                    "hash_password": "hashed_password"
                }
                user = User.from_dict(data)
                print(user.to_dict())

                user.hash_password = personalized_hasher("value_of_password")
        """
        return cls(
            id=data.get("id"),
            username=data.get("username"),
            email=data.get("email"),
            hash_password=data.get("hash_password") if not without_secrets else None,
        )


class UserPreferences(Base):
    """Persistent user interface preferences, including for the local identity.

    :param identity_key: Unique key identifying the local identity.
    :type identity_key: str
    :param user_id: Unique identifier of the user.
    :type user_id: int | None
    :param navigation: Preferred navigation style.
    :type navigation: str | None
    :param theme: Preferred theme for the user interface.
    :type theme: str

    .. table:: `user_preferences`

    .. author:: Rémi Verschuur <rverschuur@audit-io.fr>
    .. version:: 1.0.0
    """

    __tablename__ = "user_preferences"
    __table_args__ = TABLE_ARGS

    identity_key: Mapped[str] = mapped_column(
        String(100),
        primary_key=True,
        comment="Unique key identifying the local identity",
    )
    user_id: Mapped[UUID | None] = mapped_column(
        String(36),
        ForeignKey(
            foreign_key_target("users"),
            ondelete="CASCADE",
        ),
        unique=True,
        comment=_USER_ID,
    )
    navigation: Mapped[str | None] = mapped_column(
        String(20),
        comment="Preferred navigation style",
    )
    theme: Mapped[str] = mapped_column(
        String(10),
        default="system",
        nullable=False,
        comment="Preferred theme for the user interface",
    )


class Group(Base):
    """Represents a group of users.
    
    :param id: Unique identifier of the group.
    :type id: int
    :param name: Name of the group.
    :type name: str
    :param description: Description of the group.
    :type description: str
    :param users: List of users belonging to the group.
    :type users: list[User]
    
    .. methods::
        - `to_dict()`: Converts the Group object to a dictionary.
        - `from_dict()`: Creates a Group object from a dictionary.
    
    .. table:: `groups`
    
    .. author:: Rémi Verschuur <rverschuur@audit-io.fr>
    .. version:: 1.0
    """
    __tablename__ = "groups"
    __table_args__ = TABLE_ARGS

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True,
        comment="Unique identifier of the group",
    )
    name: Mapped[str] = mapped_column(
        String(50),
        unique=True,
        nullable=False,
        comment="Name of the group",
    )
    description: Mapped[str] = mapped_column(
        String(255),
        nullable=True,
        comment="Description of the group",
    )
    users: Mapped[list["User"]] = relationship(
        "User",
        secondary=lambda: Base.metadata.tables[table_key("user_groups")],
        back_populates="groups",
    )


class UserGroup(Base):
    """Represents the association between users and groups.

    :param id: Unique identifier of the user-group association.
    :type id: int
    :param user_id: Unique identifier of the user.
    :type user_id: int
    :param group_id: Unique identifier of the group.
    :type group_id: int
    :param activated: Indicates whether the association between the user and the group is active.
    :type activated: bool

    .. methods::
        - `to_dict()`: Converts the UserGroup object to a dictionary.
        - `from_dict()`: Creates a UserGroup object from a dictionary.

    .. table:: `user_groups`

    .. author:: Rémi Verschuur <rverschuur@audit-io.fr>
    .. version:: 1.0
    """
    __tablename__ = "user_groups"
    __table_args__ = (UniqueConstraint("user_id", "group_id"), TABLE_ARGS)

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True,
        comment="Unique identifier of the user-group association",
    )
    user_id: Mapped[UUID] = mapped_column(
        String(36),
        ForeignKey(foreign_key_target("users")),
        comment=_USER_ID,
    )
    group_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey(foreign_key_target("groups")),
        comment="Unique identifier of the group",
    )
    activated: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        comment="Indicates whether the association between the user and the group is active",
    )


class UserSession(Base):
    """Represents a user session.

    :param id: Unique identifier of the user session.
    :type id: int
    :param user_id: Unique identifier of the user.
    :type user_id: int
    :param session_token: Token representing the user session.
    :type session_token: str
    :param created_at: Timestamp when the session was created.
    :type created_at: datetime
    :param expires_at: Timestamp when the session expires.
    :type expires_at: datetime
    :param user: The user associated with the session.
    :type user: User

    .. methods::
        - `to_dict()`: Converts the UserSession object to a dictionary.
        - `from_dict()`: Creates a UserSession object from a dictionary.

    .. table:: `user_sessions`

    .. author:: Rémi Verschuur <rverschuur@audit-io.fr>
    .. version:: 1.0
    """
    __tablename__ = "user_sessions"
    __table_args__ = TABLE_ARGS

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True,
        comment="Unique identifier of the user session",
    )
    user_id: Mapped[UUID] = mapped_column(
        String(36),
        ForeignKey(foreign_key_target("users")),
        nullable=False,
        comment=_USER_ID,
    )
    session_token: Mapped[str] = mapped_column(
        String(255),
        unique=True,
        nullable=False,
        comment="Token representing the user session",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        default=datetime.now(timezone.utc),
        comment="Timestamp when the session was created",
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        comment="Timestamp when the session expires",
    )
    user: Mapped["User"] = relationship(
        "User",
        back_populates="sessions",
    )


class UserLoginState(Base):
    """Persistent state of a user's login attempts.
    
    :param user_id: Unique identifier of the user.
    :type user_id: int
    :param failed_attempts: Number of failed login attempts.
    :type failed_attempts: int
    :param locked: Indicates whether the user's account is locked.
    :type locked: bool

    .. author:: Rémi Verschuur <rverschuur@audit-io.fr>
    .. version:: 1.0.0
    """

    __tablename__ = "user_login_states"
    __table_args__ = TABLE_ARGS

    user_id: Mapped[UUID] = mapped_column(
        String(36),
        ForeignKey(foreign_key_target("users")),
        primary_key=True,
    )
    failed_attempts: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )
    locked: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
    )


class UserIdentity(Base):
    """Authentication provenance associated with a persisted user.

    :param user_id: Unique identifier of the user.
    :type user_id: int
    :param auth_source: Source of authentication (e.g., local, OAuth).
    :type auth_source: str
    :param issuer: Issuer of the authentication token, if applicable.
    :type issuer: str | None
    :param subject: Subject of the authentication token, if applicable.
    :type subject: str | None

    .. author:: Rémi Verschuur <rverschuur@audit-io.fr>
    .. version:: 1.0.0
    """

    __tablename__ = "user_identities"
    __table_args__ = (
        UniqueConstraint("issuer", "subject"),
        TABLE_ARGS,
    )

    user_id: Mapped[UUID] = mapped_column(
        String(36),
        ForeignKey(foreign_key_target("users")),
        primary_key=True,
        comment=_USER_ID,
    )
    auth_source: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        comment="Source of authentication (e.g., local, OAuth)",
    )
    issuer: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        comment="Issuer of the authentication token, if applicable",
    )
    subject: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        comment="Subject of the authentication token, if applicable",
    )


class AuthRuntimeState(Base):
    """Persist the authentication context currently owning the database.

    :param id: Unique identifier of the authentication runtime state.
    :type id: int
    :param auth_mode: Authentication mode currently in use.
    :type auth_mode: str
    :param issuer: Issuer of the authentication token, if applicable.
    :type issuer: str | None

    .. author:: Rémi Verschuur <rverschuur@audit-io.fr>
    .. version:: 1.0.0
    """

    __tablename__ = "auth_runtime_state"
    __table_args__ = TABLE_ARGS

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        comment="Unique identifier of the authentication runtime state",
    )
    auth_mode: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        comment="Authentication mode currently in use",
    )
    issuer: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        comment="Issuer of the authentication token, if applicable",
    )
