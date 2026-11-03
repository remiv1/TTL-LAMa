"""Persistence service for one-time CLI login tickets.

.. classes::
    - `CliLoginTicketService`: Creates and consumes short-lived CLI login tickets.

.. module_author:: Rémi Verschuur <rverschuur@audit-io.fr>
.. version:: 1.0.0
"""
from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any, cast

from sqlalchemy import delete, select, update
from sqlalchemy.engine import CursorResult
from sqlalchemy.orm import Session as ORMSession

from api.common.db_objects.cli_login_tickets import CliLoginTicket

from ._common import ServiceMixin

CLI_LOGIN_TICKET_LIFETIME = timedelta(minutes=2)


class CliLoginTicketService(ServiceMixin):
    """Create and atomically consume temporary CLI login tickets."""

    def __init__(self, db_session: ORMSession, lifetime: timedelta) -> None:
        if lifetime <= timedelta(0):
            raise ValueError("Ticket lifetime must be positive.")
        super().__init__(db_session)
        self.lifetime = lifetime

    def create(self, user_id: str) -> str:
        """Create a ticket and persist only its SHA-256 hash."""
        ticket = secrets.token_urlsafe(32)
        ticket_hash = hashlib.sha256(ticket.encode("utf-8")).hexdigest()
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        self.db_session.execute(
            delete(CliLoginTicket).where(
                (CliLoginTicket.expires_at <= now)
                | CliLoginTicket.consumed_at.is_not(None)
            )
        )
        self.db_session.add(
            CliLoginTicket(
                ticket_hash=ticket_hash,
                user_id=user_id,
                created_at=now,
                expires_at=now + self.lifetime,
            )
        )
        self.commit()
        return ticket

    def consume(self, ticket: str) -> str | None:
        """Atomically consume a valid ticket and return its user identifier."""
        ticket_hash = hashlib.sha256(ticket.encode("utf-8")).hexdigest()
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        result = cast(
            CursorResult[Any],
            self.db_session.execute(
                update(CliLoginTicket)
                .where(
                    CliLoginTicket.ticket_hash == ticket_hash,
                    CliLoginTicket.expires_at > now,
                    CliLoginTicket.consumed_at.is_(None),
                )
                .values(consumed_at=now)
            ),
        )
        if result.rowcount != 1:
            self.rollback()
            return None

        user_id = self.db_session.scalar(
            select(CliLoginTicket.user_id).where(
                CliLoginTicket.ticket_hash == ticket_hash
            )
        )
        self.commit()
        return str(user_id) if user_id is not None else None
