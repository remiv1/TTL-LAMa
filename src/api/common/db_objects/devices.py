"""Database objects for devices.

.. classes::
    - `Device`: Represents a device in the database.

.. constant::
    - `_DEVICE_ID`: Description of the unique identifier of the device in the database.

.. author:: Rémi Verschuur <rverschuur@audit-io.fr>
.. version:: 1.0
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID
from datetime import datetime, timezone

from sqlalchemy import String, Integer, ForeignKey, DateTime
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ._common import Base, TABLE_ARGS

if TYPE_CHECKING:
    from .users import User

_DEVICE_ID = "Unique identifier of the device"

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

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        index=True,
        comment=_DEVICE_ID,
    )
    user_id: Mapped[UUID] = mapped_column(
        String(36),
        ForeignKey("users.id"),
        nullable=False,
        comment="Unique identifier of the user owning the device",
    )
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
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        unique=False,
        default=datetime.now(timezone.utc),
        comment="Timestamp indicating when the device was created",
    )
    revoked_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=True,
        unique=False,
        comment="Timestamp indicating when the device was revoked",
    )

    user: Mapped["User"] = relationship(
        "User",
        back_populates="devices",
        uselist=False,
    )
