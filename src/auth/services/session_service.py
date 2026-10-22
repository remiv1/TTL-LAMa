"""Persistent authentication session management.

.. classes::
    - `SessionService` class responsible for managing user sessions.

.. module_author:: Rémi Verschuur <rverschuur@audit-io.fr>
.. version:: 1.0
"""
from __future__ import annotations

import logging
import hashlib
import secrets
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session, scoped_session
from sqlalchemy.exc import SQLAlchemyError

from api.common.db_objects.users import UserSession

LOGGER = logging.getLogger(__name__)

class SessionService:
    """Create, retrieve and delete TTL-LAMa sessions.

    :param db_session: Scoped SQLAlchemy session for database interactions.
    :type db_session: scoped_session[Session]
    :param lifetime: Duration for which the session is valid.
    :type lifetime: timedelta

    :raises SQLAlchemyError: If committing the session to the database fails.

    .. methods::
        - `create` method to create a new session.
        - `get_user_id` method to retrieve the user ID associated with a session token.
        - `delete` method to delete a session by its token.
    
    .. staticmethods::
        - `_digest` method to hash the session token.
        - `_commit` method to commit the session to the database safely.
    
    .. author:: Rémi Verschuur <rverschuur@audit-io.fr>
    .. version:: 1.0.0
    """

    def __init__(
        self,
        db_session: scoped_session[Session],
        lifetime: timedelta = timedelta(hours=12),
    ) -> None:
        """Initialize the SessionService with a database session and session lifetime.

        :param db_session: Scoped SQLAlchemy session for database interactions.
        :type db_session: scoped_session[Session]
        :param lifetime: Duration for which the session is valid.
        :type lifetime: timedelta

        :raises SQLAlchemyError: If committing the session to the database fails.
        """
        self.db_session = db_session
        self.lifetime = lifetime

    def create(self, user_id: int) -> str:
        """Create a session and returns its opaque token.
        :param user_id: ID of the user for whom the session is being created.
        :type user_id: int

        :return: The opaque session token.
        :rtype: str
        """
        token = secrets.token_urlsafe(48)
        now = datetime.now(timezone.utc)
        record = UserSession(
            user_id=user_id,
            session_token=self._digest(token),
            created_at=now,
            expires_at=now + self.lifetime,
        )
        session = self.db_session()
        session.add(record)
        self._commit(session)
        return token

    def get_user_id(self, token: str | None) -> int | None:
        """Return the user ID associated with the token if the session is valid.

        :param token: The opaque session token.
        :type token: str | None

        :return: The user ID if the session is valid, otherwise None.
        :rtype: int | None
        """
        if not token:
            return None
        session = self.db_session()
        record = session.scalar(
            select(UserSession).where(UserSession.session_token == self._digest(token))
        )
        if record is None:
            LOGGER.debug("Session not found")
            return None
        expires_at = record.expires_at
        if expires_at.tzinfo is None:
            LOGGER.debug("Session expiration time had no timezone info, assuming UTC")
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        if expires_at <= datetime.now(timezone.utc):
            LOGGER.debug("Session expired")
            session.delete(record)
            self._commit(session)
            return None
        return record.user_id

    def delete(self, token: str | None) -> None:
        """Delete the session associated with the token.

        :param token: The opaque session token.
        :type token: str | None

        :return: None
        :rtype: None
        """
        if not token:
            return
        session = self.db_session()
        stmt = select(UserSession).where(UserSession.session_token == self._digest(token))
        record = session.scalar(stmt)
        if record is not None:
            LOGGER.debug("Deleting session")
            session.delete(record)
            self._commit(session)

    @staticmethod
    def _digest(token: str) -> str:
        """Return the SHA-256 hash of the given token.

        :param token: The opaque session token.
        :type token: str

        :return: The SHA-256 hash of the token.
        :rtype: str
        """
        return hashlib.sha256(token.encode("utf-8")).hexdigest()

    @staticmethod
    def _commit(session: Session) -> None:
        """Commit the session to the database safely.

        :param session: The SQLAlchemy session to commit.
        :type session: Session

        :raises SQLAlchemyError: If committing the session to the database fails.
        """
        try:
            session.commit()
        except SQLAlchemyError as e:
            LOGGER.exception(
                "Failed to commit session to the database : %s",
                e,
                exc_info=True,
            )
            session.rollback()
            raise SQLAlchemyError("Failed to commit session to the database.") from e
