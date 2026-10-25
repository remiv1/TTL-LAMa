"""Database objects for users.

.. classes::
    - `User`: Represents a user in the database.
    - `UserSession`: Represents a session of a user in the database.
    - `UserLoginState`: Represents a user's login attempt state in the database.
    - `AuthRuntimeState`: Represents the authentication runtime state of a user in the database.
    - `UserIdentity`: Represents the identity of a user in the database.

.. constant::
    - `_USER_ID`: Description of the unique identifier of the user in the database.

.. author:: Rémi Verschuur <rverschuur@audit-io.fr>
.. version:: 1.0
"""
from __future__ import annotations

from typing import TYPE_CHECKING
from datetime import datetime, timezone
from uuid import uuid4, UUID

from sqlalchemy import String, DateTime, Boolean
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ._common import Base, TABLE_ARGS

if TYPE_CHECKING:
    from .sessions import Session
    from .credentials import Credentials
    from .devices import Device
    from .profiles import Profile
    from .login_state import LoginState
    from .oidc import OIDCUser

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
        String(254),
        unique=True,
        nullable=True,
        comment="Email address of the user",
    )
    enabled: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        unique=False,
        default=True,
        comment="Indicates whether the user is enabled",
    )
    is_admin: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        unique=False,
        default=False,
        comment="Indicates whether the user has admin privileges",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        unique=False,
        default=datetime.now(timezone.utc),
        comment="Timestamp indicating when the user was created",
    )
    last_login: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=True,
        unique=False,
        comment="Timestamp indicating the last login of the user",
    )

    oidc_users: Mapped[list["OIDCUser"]] = relationship(
        "OIDCUser",
        back_populates="user",
        uselist=True,
    )
    sessions: Mapped[list["Session"]] = relationship(
        "Session",
        back_populates="user",
        uselist=True,
    )
    credentials: Mapped[list["Credentials"]] = relationship(
        "Credentials",
        back_populates="user",
        uselist=True,
    )
    devices: Mapped[list["Device"]] = relationship(
        "Device",
        back_populates="user",
        uselist=True,
    )
    profiles: Mapped[list["Profile"]] = relationship(
        "Profile",
        secondary="profile_users",
        back_populates="users",
        viewonly=True,
    )
    login_state: Mapped["LoginState"] = relationship(
        "LoginState",
        back_populates="user",
        uselist=False,
    )
