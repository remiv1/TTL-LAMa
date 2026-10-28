"""Database objects for devices.

.. classes::
    - `Device`: Represents a device in the database.

.. constant::
    - `_DEVICE_ID`: Description of the unique identifier of the device in the database.

.. author:: Rémi Verschuur <rverschuur@audit-io.fr>
.. version:: 1.0
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional
from uuid import UUID
from datetime import datetime

from sqlalchemy import String
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
    from .users import User
    from .leases import Lease

class Device(Base):
    """Represents a device in the database.

    :param id: Unique identifier of the device.
    :type id: int
    :param user_id: Unique identifier of the user owning the device.
    :type user_id: int

    .. table:: `devices`

    .. author:: Rémi Verschuur <rverschuur@audit-io.fr>
    .. version:: 1.0
    """
    __tablename__ = "devices"
    __table_args__ = TABLE_ARGS

    id: Mapped[int] = numerical_pk_column()
    user_id: Mapped[UUID] = user_id_column()
    name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        comment="Name of the device",
    )
    public_key: Mapped[str] = mapped_column(
        String(512),
        nullable=False,
        comment="Public key of the device",
    )
    created_at: Mapped[datetime] = created_at_column()
    revoked_at: Mapped[Optional[datetime]] = revoked_at_column()

    user: Mapped["User"] = relationship(
        "User",
        back_populates="devices",
        uselist=False,
    )
    leases: Mapped[list["Lease"]] = relationship(
        "Lease",
        back_populates="device",
        uselist=True,
    )
