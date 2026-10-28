"""Database objects for user sessions.

.. classes::
    - `UserSession`: Represents a session of a user in the database.

.. author:: Rémi Verschuur <rverschuur@audit-io.fr>
.. version:: 1.0
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Optional
from datetime import datetime
from uuid import UUID

from sqlalchemy import String, DateTime
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

class Session(Base):
    """Represents a user session.

    :param id: Unique identifier of the user session.
    :type id: int
    :param user_id: Unique identifier of the user.
    :type user_id: int
    :param token_hash: Hash of the token representing the user session.
    :type token_hash: str
    :param created_at: Timestamp when the session was created.
    :type created_at: datetime
    :param expires_at: Timestamp when the session expires.
    :type expires_at: datetime
    :param revoked_at: Timestamp when the session was revoked.
    :type revoked_at: datetime
    :param last_seen_at: Timestamp when the session was last seen.
    :type last_seen_at: datetime

    .. methods::
        - `to_dict()`: Converts the UserSession object to a dictionary.
        - `from_dict()`: Creates a UserSession object from a dictionary.

    .. table:: `user_sessions`

    .. author:: Rémi Verschuur <rverschuur@audit-io.fr>
    .. version:: 1.0
    """
    __tablename__ = "user_sessions"
    __table_args__ = TABLE_ARGS

    id: Mapped[int] = numerical_pk_column()
    user_id: Mapped[UUID] = user_id_column()
    token_hash: Mapped[str] = mapped_column(
        String(255),
        unique=True,
        nullable=False,
        comment="Hash of the token representing the user session",
    )
    created_at: Mapped[datetime] = created_at_column()
    expires_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        comment="Timestamp when the session expires",
    )
    revoked_at: Mapped[Optional[datetime]] = revoked_at_column()
    last_seen_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime,
        nullable=True,
        comment="Timestamp when the session was last seen",
    )

    user: Mapped["User"] = relationship(
        "User",
        back_populates="sessions",
        uselist=False,
    )
