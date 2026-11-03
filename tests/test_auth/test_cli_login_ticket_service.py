"""Tests for the one-time CLI login ticket service."""

import hashlib
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from api.common.db_objects import User
from api.common.db_objects.cli_login_tickets import CliLoginTicket
from auth.services import CliLoginTicketService, UserService


def test_ticket_is_hashed_and_can_only_be_consumed_once(
    user_service: UserService,
    user_with_oidc_identity: User,
) -> None:
    """A ticket is stored hashed and its exchange succeeds at most once."""
    ticket_service = CliLoginTicketService(
        user_service.db_session,
        timedelta(minutes=2),
    )

    ticket = ticket_service.create(str(user_with_oidc_identity.id))
    ticket_hash = hashlib.sha256(ticket.encode("utf-8")).hexdigest()
    stored_ticket = user_service.db_session.get(CliLoginTicket, ticket_hash)

    assert ticket
    assert stored_ticket is not None
    assert stored_ticket.ticket_hash != ticket
    assert ticket_service.consume(ticket) == str(user_with_oidc_identity.id)
    assert ticket_service.consume(ticket) is None


def test_expired_ticket_cannot_be_consumed(
    user_service: UserService,
    user_with_oidc_identity: User,
) -> None:
    """An expired ticket is rejected even if it has not been consumed."""
    ticket_service = CliLoginTicketService(
        user_service.db_session,
        timedelta(minutes=2),
    )
    ticket = ticket_service.create(str(user_with_oidc_identity.id))
    ticket_hash = hashlib.sha256(ticket.encode("utf-8")).hexdigest()
    stored_ticket = user_service.db_session.scalar(
        select(CliLoginTicket).where(CliLoginTicket.ticket_hash == ticket_hash)
    )
    assert stored_ticket is not None
    stored_ticket.expires_at = (
        datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(seconds=1)
    )
    user_service.db_session.commit()

    assert ticket_service.consume(ticket) is None
