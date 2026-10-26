"""Module for user credentials database object.

.. classes::
    - `Credentials`: Represents the credentials of a user in the database.

.. author:: Rémi Verschuur <rverschuur@audit-io.fr>
.. version:: 1.0.0
"""
from __future__ import annotations

from uuid import UUID

from typing import TYPE_CHECKING
from sqlalchemy import Integer, String, CheckConstraint, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ._common import Base, TABLE_ARGS, foreign_key_target
from ..other_objects import AuthMethod
if TYPE_CHECKING:
    from .users import User

_USER_ID = "Unique identifier of the user"

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

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True,
        comment="Unique identifier of the user credentials",
    )
    user_id: Mapped[UUID] = mapped_column(
        String(36),
        ForeignKey(foreign_key_target("users")),
        nullable=False,
        comment=_USER_ID,
    )
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
    user: Mapped["User"] = relationship(
        "User",
        back_populates="credentials",
        uselist=False,
    )
