"""Module for managing user sessions.

.. classes::
    - `SessionService` class responsible for managing user sessions.

    
.. module_author:: Rémi Verschuur <rverschuur@audit-io.fr>
.. version:: 1.0.0
"""
from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session as ORMSession

from api.common.db_objects.sessions import Session as UserSession

from ._common import ServiceMixin


class SessionService(ServiceMixin):
    """Service class responsible for managing user sessions.
    
    :param db_session: The database session used for interacting with the user sessions.
    :type db_session: ORMSession
    :param lifetime: The lifetime of the user session.
    :type lifetime: timedelta

    :raises ValueError: If the session lifetime is not positive.
    
    ..author:: Rémi Verschuur <rverschuur@audit-io.fr>
    ..version:: 1.0.0
    """

    def __init__(self, db_session: ORMSession, lifetime: timedelta) -> None:
        if lifetime <= timedelta(0):
            raise ValueError("Session lifetime must be positive.")
        super().__init__(db_session)
        self.lifetime = lifetime

    def create(self, user_id: UUID | str) -> str:
        """Create a new user session.
        
        :param user_id: The ID of the user for whom the session is being created.
        :type user_id: UUID | str

        :return: The session token.
        :rtype: str
        """
        token = secrets.token_urlsafe(32)
        created_at = datetime.now(timezone.utc)
        hashed_token = hashlib.sha256(token.encode("utf-8")).hexdigest()

        session = UserSession(
            user_id=str(user_id),
            token_hash=hashed_token,
            created_at=created_at,
            expires_at=created_at + self.lifetime
        )

        self.db_session.add(session)
        self.commit()

        return token

    def get_user_id(self, token: str | None) -> str | None:
        """Retrieve the user ID associated with a given session token.

        :param token: The session token.
        :type token: str

        :return: The user ID if the session is valid, None otherwise.
        :rtype: str | None
        """
        if not token:
            return None

        hashed_token = hashlib.sha256(token.encode("utf-8")).hexdigest()
        now = datetime.now(timezone.utc).replace(tzinfo=None)

        stmt = select(UserSession.user_id).where(
            UserSession.token_hash == hashed_token,
            UserSession.expires_at > now,
            UserSession.revoked_at.is_(None),
        )
        user_id = self.db_session.scalar(stmt)

        return str(user_id) if user_id is not None else None

    def revoke(self, token: str | None) -> None:
        """Revoke a user session.

        :param token: The session token to revoke.
        :type token: str
        """
        if not token:
            return

        token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
        stmt = select(UserSession).where(UserSession.token_hash == token_hash)
        session = self.db_session.scalar(stmt)

        if session is None or session.revoked_at is not None:
            return
        session.revoked_at = datetime.now(timezone.utc).replace(tzinfo=None)

        self.commit()
