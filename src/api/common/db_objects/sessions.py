"""Database objects for user sessions.

.. classes::
    - `UserSession`: Represents a session of a user in the database.

.. author:: Rémi Verschuur <rverschuur@audit-io.fr>
.. version:: 1.0
"""
from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import Integer, String, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from ._common import Base, TABLE_ARGS, foreign_key_target

_USER_ID = "Unique identifier of the user"

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

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True,
        comment="Unique identifier of the user session",
    )
    user_id: Mapped[UUID] = mapped_column(
        String(36),
        ForeignKey(foreign_key_target("users")),
        nullable=False,
        comment=_USER_ID,
    )
    token_hash: Mapped[str] = mapped_column(
        String(255),
        unique=True,
        nullable=False,
        comment="Hash of the token representing the user session",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        default=datetime.now(timezone.utc),
        comment="Timestamp when the session was created",
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        comment="Timestamp when the session expires",
    )
    revoked_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=True,
        comment="Timestamp when the session was revoked",
    )
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=True,
        comment="Timestamp when the session was last seen",
    )
