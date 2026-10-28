"""Module for user credentials database object.

.. classes::
    - `Credentials`: Represents the credentials of a user in the database.

.. author:: Rémi Verschuur <rverschuur@audit-io.fr>
.. version:: 1.0.0
"""
from __future__ import annotations

from uuid import UUID
from datetime import datetime

from typing import TYPE_CHECKING, Optional
from sqlalchemy import String, CheckConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ._common import (
    Base,
    TABLE_ARGS,
    user_id_column,
    revoked_at_column,
    numerical_pk_column,
)
from ..other_objects import AuthMethod
if TYPE_CHECKING:
    from .users import User

class Credentials(Base):
    """Represents the credentials of a user.

    :param id: Unique identifier of the user credentials.
    :type id: int
    :param user_id: Unique identifier of the user.
    :type user_id: int
    :param hash_password: Hashed password of the user.
    :type hash_password: str

    .. author:: Rémi Verschuur <rverschuur@audit-io.fr>
    .. version:: 1.0.0
    """

    __tablename__ = "user_credentials"
    __table_args__ = (
        CheckConstraint(
            f"auth_method IN ({', '.join(f"'{m.value}'" for m in AuthMethod)})",
            name="auth_method_check",
        ),
        TABLE_ARGS,
    )

    id: Mapped[int] = numerical_pk_column()
    user_id: Mapped[UUID] = user_id_column()
    auth_method: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        comment="Authentication method of the user",
    )
    hash_password: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        comment="Hashed password of the user",
    )
    revoked_at: Mapped[Optional[datetime]] = revoked_at_column()

    user: Mapped["User"] = relationship(
        "User",
        back_populates="credentials",
        uselist=False,
    )
