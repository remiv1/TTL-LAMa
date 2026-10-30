"""Lease queries and revocations shared by administrative operations.

.. functions::
    - `utcnow`: Get the current UTC time as a naive datetime object.
    - `lease_status`: Determine the status of a lease ("revoked", "expired", or "active").

.. classes::
    - `LeaseRepository`: Repository for managing lease entities.

.. author:: Rémi Verschuur <rverschuur@audit-io.fr>
.. version:: 1.0.0
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select, update
from sqlalchemy.orm import Session
from sqlalchemy.sql.elements import ColumnElement

from api.common.db_objects.leases import Lease
from api.common.db_objects.profiles import ProfileUser
from .base import Repository


def utcnow() -> datetime:
    """Use naive UTC consistently with lease expiration storage.
    
    :return: The current UTC time as a naive datetime object.
    :rtype: datetime
    """
    return datetime.now(timezone.utc).replace(tzinfo=None)


def lease_status(lease: Lease) -> str:
    """Resolve revocation before expiration.
    
    :param lease: The lease to check.
    :type lease: Lease
    :return: The status of the lease ("revoked", "expired", or "active").
    :rtype: str
    """
    if lease.revoked_at is not None:
        return "revoked"
    end = lease.ended_at
    if end.tzinfo is not None:
        end = end.astimezone(timezone.utc).replace(tzinfo=None)
    return "expired" if end <= utcnow() else "active"


class LeaseRepository(Repository[Lease]):
    """Query and revoke leases without removing their history.

    :param session: The SQLAlchemy session to use for database operations.
    :type session: Session

    .. author:: Rémi Verschuur <rverschuur@audit-io.fr>
    .. version:: 1.0.0
    """

    def __init__(self, session: Session) -> None:
        super().__init__(session, Lease)

    def find(
        self,
        *,
        user: str | None = None,
        device: int | None = None,
        profile: int | None = None,
        status: str | None = None,
    ) -> list[Lease]:
        """Combine optional filters using AND.
        
        :param user: Filter by user ID.
        :type user: str | None
        :param device: Filter by device ID.
        :type device: int | None
        :param profile: Filter by profile ID.
        :type profile: int | None
        :param status: Filter by lease status ("revoked", "expired", or "active").
        :type status: str | None
        :return: A list of leases matching the specified filters.
        :rtype: list[Lease]
        """
        conditions: list[ColumnElement[bool]] = []
        if user is not None:
            conditions.append(Lease.user_id == user)
        if device is not None:
            conditions.append(Lease.device_id == device)
        if profile is not None:
            conditions.append(Lease.profile_user_id.in_(
                select(ProfileUser.id).where(ProfileUser.profile_id == profile)
            ))
        if status == "revoked":
            conditions.append(Lease.revoked_at.is_not(None))
        elif status == "expired":
            conditions.extend([Lease.revoked_at.is_(None), Lease.ended_at <= utcnow()])
        elif status == "active":
            conditions.extend([Lease.revoked_at.is_(None), Lease.ended_at > utcnow()])
        elif status is not None:
            raise ValueError("Invalid lease status")
        return self.list(*conditions)

    def revoke(self, lease: Lease) -> Lease:
        """Revoke idempotently, preserving the first revocation time.
        
        :param lease: The lease to revoke.
        :type lease: Lease
        :return: The revoked lease.
        :rtype: Lease
        """
        if lease.revoked_at is None:
            lease.revoked_at = utcnow()
        return lease

    def revoke_matching(self, *conditions: ColumnElement[bool]) -> None:
        """Revoke leases affected by another domain operation.
        
        :param conditions: Conditions to match leases for revocation.
        :type conditions: ColumnElement[bool]
        """
        self.session.execute(
            update(Lease).where(Lease.revoked_at.is_(None), *conditions)
            .values(revoked_at=utcnow())
        )
