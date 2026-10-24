"""Database object for user login state.

.. classes::
    - `UserLoginState`: Represents the persistent state of a user's login attempts.

.. author:: Rémi Verschuur <rverschuur@audit-io.fr>
.. version:: 1.0.0
"""
from __future__ import annotations

from uuid import UUID
from sqlalchemy import Integer, String, Boolean, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from ._common import Base, TABLE_ARGS, foreign_key_target

_USER_ID = "Unique identifier of the user"

class LoginState(Base):
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
        comment=_USER_ID,
    )
    failed_attempts: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        comment="Number of failed login attempts",
    )
    locked: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        comment="Indicates whether the user's account is locked",
    )
