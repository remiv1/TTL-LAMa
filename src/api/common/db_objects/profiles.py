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
from typing import TYPE_CHECKING, Optional
from datetime import datetime

from sqlalchemy import String, Integer, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ._common import (
    Base,
    TABLE_ARGS,
    numerical_pk_column,
    created_at_column,
    user_id_column,
    revoked_at_column,
)

if TYPE_CHECKING:
    from .users import User
    from .leases import Lease

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

    id: Mapped[int] = numerical_pk_column()
    name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        comment="Name of the profile",
    )
    created_at: Mapped[datetime] = created_at_column()
    revoked_at: Mapped[Optional[datetime]] = revoked_at_column()
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
    user_id: Mapped[UUID] = user_id_column()
    created_at: Mapped[datetime] = created_at_column()
    revoked_at: Mapped[Optional[datetime]] = revoked_at_column()
    profile: Mapped["Profile"] = relationship(
        "Profile",
        back_populates="profile_user",
    )
    user: Mapped["User"] = relationship("User")
    leases: Mapped[list["Lease"]] = relationship(
        "Lease",
        back_populates="profile_user",
    )
