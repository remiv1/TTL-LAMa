"""Module for database objects related to leases.

.. classes::
    - `Lease`: Represents a lease in the database.

.. constant::
    - `_LEASE_ID`: Description of the unique identifier of the lease in the database.

.. author:: Rémi Verschuur <rverschuur@audit-io.fr>
.. version:: 1.0
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Optional
from uuid import UUID
from datetime import datetime

from sqlalchemy import Integer, ForeignKey, DateTime
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ._common import (
    Base,
    TABLE_ARGS,
    created_at_column,
    user_id_column,
    revoked_at_column,
    numerical_pk_column,
)

if TYPE_CHECKING:
    from .devices import Device
    from .users import User
    from .profiles import Profile, ProfileUser

class Lease(Base):
    """Represents a lease in the database.

    :param id: Unique identifier of the lease.
    :type id: int
    :param device_id: Unique identifier of the device associated with the lease.
    :type device_id: int
    :param user_id: Unique identifier of the user associated with the lease.
    :type user_id: int

    .. table:: `leases`

    .. author:: Rémi Verschuur <rverschuur@audit-io.fr>
    .. version:: 1.0
    """
    __tablename__ = "leases"
    __table_args__ = TABLE_ARGS

    id: Mapped[int] = numerical_pk_column()
    device_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("devices.id"),
        nullable=False,
        comment="Unique identifier of the device associated with the lease",
    )
    user_id: Mapped[UUID] = user_id_column()
    profile_user_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("profile_users.id"),
        nullable=False,
        comment="Unique identifier of the profile user associated with the lease",
    )
    created_at: Mapped[datetime] = created_at_column()
    ended_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        unique=False,
        comment="Timestamp indicating when the lease ended",
    )
    revoked_at: Mapped[Optional[datetime]] = revoked_at_column()

    device: Mapped["Device"] = relationship(
        "Device",
        back_populates="leases",
        uselist=False,
    )
    user: Mapped["User"] = relationship(
        "User",
        back_populates="leases",
        uselist=False,
    )
    profile_user: Mapped["ProfileUser"] = relationship(
        "ProfileUser",
        back_populates="leases",
        uselist=False,
    )
    profile: Mapped["Profile"] = relationship(
        "Profile",
        secondary="profile_users",
        primaryjoin="Lease.profile_user_id==ProfileUser.id",
        secondaryjoin="ProfileUser.profile_id==Profile.id",
        uselist=False,
        viewonly=True,
    )
