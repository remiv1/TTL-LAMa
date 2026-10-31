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

from api.common.db_objects.devices import Device
from api.common.db_objects.leases import Lease
from api.common.db_objects.profile_policy import ProfilePolicy
from api.common.db_objects.profiles import Profile, ProfileUser
from api.config.c_profiles import parse_duration
from .base import ConflictError, NotFoundError, Repository


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

    def get_owned(self, identifier: int, user_id: str) -> Lease:
        """Retrieve a lease only when it belongs to the given user."""
        lease = self.session.scalar(select(Lease).where(
            Lease.id == identifier, Lease.user_id == user_id
        ))
        if lease is None:
            raise NotFoundError("Lease not found")
        return lease

    def create(
        self,
        *,
        user_id: str,
        device_id: int,
        profile_id: int,
        duration: str | None = None,
    ) -> Lease:
        """Create a lease within the user's device and profile policy.

        :param user_id: The identifier of the authenticated user.
        :type user_id: str
        :param device_id: The identifier of an active device owned by the user.
        :type device_id: int
        :param profile_id: The identifier of an actively assigned profile.
        :type profile_id: int
        :param duration: Requested duration, or the profile default when omitted.
        :type duration: str | None
        :return: The staged lease.
        :rtype: Lease
        :raises NotFoundError: If the device or profile is not available to the user.
        :raises ConflictError: If the profile has no policy or duration exceeds its maximum.
        :raises ValueError: If the requested duration is invalid.
        """
        device = self.session.scalar(select(Device).where(
            Device.id == device_id,
            Device.user_id == user_id,
            Device.revoked_at.is_(None),
        ))
        if device is None:
            raise NotFoundError("Active device not found")

        assignment = self.session.scalar(
            select(ProfileUser)
            .join(Profile, Profile.id == ProfileUser.profile_id)
            .where(
                ProfileUser.user_id == user_id,
                ProfileUser.profile_id == profile_id,
                ProfileUser.revoked_at.is_(None),
                Profile.revoked_at.is_(None),
            )
        )
        if assignment is None:
            raise NotFoundError("Active profile assignment not found")

        policy = self.session.get(ProfilePolicy, profile_id)
        if policy is None:
            raise ConflictError("Assigned profile has no access policy")

        selected_duration = duration or policy.default_duration
        requested = parse_duration(selected_duration)
        if requested > parse_duration(policy.maximum_duration):
            raise ConflictError("Requested duration exceeds the profile maximum")

        return self.add(Lease(
            device_id=device_id,
            user_id=user_id,
            profile_user_id=assignment.id,
            ended_at=utcnow() + requested,
        ))

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
