"""Module for database objects related to profiles.

.. classes::
    - `Profile`: Represents a profile in the database.

.. constant::
    - `_PROFILE_ID`: Description of the unique identifier of the profile in the database.

.. author:: Rémi Verschuur <rverschuur@audit-io.fr>
.. version:: 1.0
"""
from __future__ import annotations

from uuid import UUID
from typing import TYPE_CHECKING
from datetime import datetime, timezone

from sqlalchemy import String, Integer, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ._common import Base, TABLE_ARGS

if TYPE_CHECKING:
    from .users import User
    from .leases import Lease

_PROFILE_ID = "Unique identifier of the profile"

class Profile(Base):
    """Represents a profile in the database.

    :param id: Unique identifier of the profile.
    :type id: int
    :param user_id: Unique identifier of the user associated with the profile.
    :type user_id: int

    .. table:: `profiles`

    .. author:: Rémi Verschuur <rverschuur@audit-io.fr>
    .. version:: 1.0
    """
    __tablename__ = "profiles"
    __table_args__ = TABLE_ARGS

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        index=True,
        comment=_PROFILE_ID,
    )
    name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        comment="Name of the profile",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        unique=False,
        default=datetime.now(timezone.utc),
        comment="Timestamp indicating when the profile was created",
    )
    revoked_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=True,
        unique=False,
        comment="Timestamp indicating when the profile was revoked",
    )
    profile_user: Mapped[list["ProfileUser"]] = relationship(
        "ProfileUser",
        back_populates="profile",
    )
    users: Mapped[list["User"]] = relationship(
        "User",
        secondary="profile_users",
        back_populates="profiles",
        viewonly=True
    )

class ProfileUser(Base):
    """Represents a profile user association in the database.

    :param id: Unique identifier of the profile user association.
    :type id: int
    :param profile_id: Unique identifier of the profile associated with the user.
    :type profile_id: int
    :param user_id: Unique identifier of the user associated with the profile.
    :type user_id: int

    .. table:: `profile_users`

    .. author:: Rémi Verschuur <rverschuur@audit-io.fr>
    .. version:: 1.0
    """
    __tablename__ = "profile_users"
    __table_args__ = TABLE_ARGS

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        index=True,
        comment="Unique identifier of the profile user association",
    )
    profile_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("profiles.id"),
        nullable=False,
        comment="Unique identifier of the profile associated with the user",
    )
    user_id: Mapped[UUID] = mapped_column(
        String(36),
        ForeignKey("users.id"),
        nullable=False,
        comment="Unique identifier of the user associated with the profile",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        unique=False,
        default=datetime.now(timezone.utc),
        comment="Timestamp indicating when the profile user association was created",
    )
    revoked_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=True,
        unique=False,
        comment="Timestamp indicating when the profile user association was revoked",
    )
    profile: Mapped["Profile"] = relationship(
        "Profile",
        back_populates="profile_user",
    )
    user: Mapped["User"] = relationship("User")
    leases: Mapped[list["Lease"]] = relationship(
        "Lease",
        back_populates="profile_user",
    )
