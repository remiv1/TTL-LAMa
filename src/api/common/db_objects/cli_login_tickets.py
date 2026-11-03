"""Database objects for temporary CLI authentication tickets.

.. classes::
    - `CliLoginTicket`: A one-time ticket exchanged for a CLI session.

.. module_author:: Rémi Verschuur <rverschuur@audit-io.fr>
.. version:: 1.0.0
"""
from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, String
from sqlalchemy.orm import Mapped, mapped_column

from ._common import Base, TABLE_ARGS, user_id_column


class CliLoginTicket(Base):
    """Represent a short-lived, single-use CLI login ticket."""

    __tablename__ = "cli_login_tickets"
    __table_args__ = TABLE_ARGS

    ticket_hash: Mapped[str] = mapped_column(
        String(64),
        primary_key=True,
        nullable=False,
        comment="SHA-256 hash of the one-time CLI ticket",
    )
    user_id: Mapped[UUID] = user_id_column()
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        comment="Ticket creation timestamp",
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        index=True,
        comment="Ticket expiration timestamp",
    )
    consumed_at: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True,
        comment="Ticket consumption timestamp",
    )
