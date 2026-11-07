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
from ipaddress import ip_network
from typing import cast

from sqlalchemy import select, update
from sqlalchemy.engine import CursorResult
from sqlalchemy.orm import Session, object_session
from sqlalchemy.sql.elements import ColumnElement

from api.common.db_objects import (
    UserDevice,
    UserLease,
    ProfileUser,
    Profile,
    LeaseProvisioning,
    ProvisioningLock,
    User,
)
from api.common.db_objects.profile_policy import ProfilePolicy
from api.config.c_profiles import parse_duration
from .base import ConflictError, NotFoundError, Repository


def utcnow() -> datetime:
    """Use naive UTC consistently with lease expiration storage.
    
    :return: The current UTC time as a naive datetime object.
    :rtype: datetime
    """
    return datetime.now(timezone.utc).replace(tzinfo=None)


def lease_status(lease: UserLease) -> str:
    """Resolve revocation before expiration.
    
    :param lease: The lease to check.
    :type lease: UserLease
    :return: The status of the lease ("revoked", "expired", or "active").
    :rtype: str
    """
    if lease.revoked_at is not None:
        return "revoked"
    end = lease.ended_at
    if end.tzinfo is not None:
        end = end.astimezone(timezone.utc).replace(tzinfo=None)
    if end <= utcnow():
        return "expired"
    session = object_session(lease)
    provisioning = session.get(LeaseProvisioning, lease.id) if session else None
    if provisioning is not None and provisioning.state != "applied":
        return "failed" if provisioning.error else "pending"
    return "active"


class LeaseRepository(Repository[UserLease]):
    """Query and revoke leases without removing their history.

    :param session: The SQLAlchemy session to use for database operations.
    :type session: Session

    .. author:: Rémi Verschuur <rverschuur@audit-io.fr>
    .. version:: 1.0.0
    """

    def __init__(self, session: Session) -> None:
        super().__init__(session, UserLease)

    def _ensure_available(self, interface: str, public_key: str, networks: list[str]) -> None:
        reservations = self.session.scalars(
            select(LeaseProvisioning)
            .where(LeaseProvisioning.state != "deleted")
            .with_for_update()
        ).all()
        for reservation in reservations:
            document = reservation.document
            if document.get("interface") != interface:
                continue
            if document.get("public_key") == public_key:
                raise ConflictError("The device already has a reserved lease on this interface")
            if self._networks_overlap(document.get("addresses"), networks):
                raise ConflictError("The profile networks overlap an existing lease")

    @staticmethod
    def _networks_overlap(addresses: object, networks: list[str]) -> bool:
        if not isinstance(addresses, list):
            raise RuntimeError("Invalid stored VPN reservation")
        requested_networks = [ip_network(network) for network in networks]
        for value in cast(list[object], addresses):
            if not isinstance(value, str):
                raise RuntimeError("Invalid stored VPN reservation")
            existing = ip_network(value)
            if any(network.version == existing.version and network.overlaps(existing)
                   for network in requested_networks):
                return True
        return False

    def find(
        self,
        *,
        user: str | None = None,
        device: int | None = None,
        profile: int | None = None,
        status: str | None = None,
    ) -> list[UserLease]:
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
        :rtype: list[UserLease]
        """
        conditions: list[ColumnElement[bool]] = []
        if user is not None:
            conditions.append(UserLease.user_id == user)
        if device is not None:
            conditions.append(UserLease.device_id == device)
        if profile is not None:
            conditions.append(UserLease.profile_user_id.in_(
                select(ProfileUser.id).where(ProfileUser.profile_id == profile)
            ))
        if status == "revoked":
            conditions.append(UserLease.revoked_at.is_not(None))
        elif status == "expired":
            conditions.extend([UserLease.revoked_at.is_(None), UserLease.ended_at <= utcnow()])
        elif status == "active":
            conditions.extend([UserLease.revoked_at.is_(None), UserLease.ended_at > utcnow()])
            conditions.append(~UserLease.id.in_(select(LeaseProvisioning.lease_id).where(
                LeaseProvisioning.state != "applied"
            )))
        elif status is not None:
            raise ValueError("Invalid lease status")
        return self.list(*conditions)

    def get_owned(self, identifier: int, user_id: str) -> UserLease:
        """Retrieve a lease only when it belongs to the given user."""
        lease = self.session.scalar(select(UserLease).where(
            UserLease.id == identifier, UserLease.user_id == user_id
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
    ) -> UserLease:
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
        :rtype: UserLease
        :raises NotFoundError: If the device or profile is not available to the user.
        :raises ConflictError: If the profile has no policy or duration exceeds its maximum.
        :raises ValueError: If the requested duration is invalid.
        """
        result = cast(
            CursorResult[object],
            self.session.execute(
                update(ProvisioningLock)
                    .where(ProvisioningLock.id == 1)
                    .values(version=ProvisioningLock.version + 1)
            )
        )
        if result.rowcount != 1:
            raise RuntimeError("The provisioning lock is not initialized")

        user = self.session.scalar(select(User).where(
            User.id == user_id, User.enabled.is_(True)
        ).with_for_update().execution_options(populate_existing=True))
        if user is None:
            raise NotFoundError("Active user not found")
        device = self.session.scalar(
            select(UserDevice).where(
                UserDevice.id == device_id,
                UserDevice.user_id == user_id,
                UserDevice.revoked_at.is_(None),
            ).with_for_update().execution_options(populate_existing=True)
        )
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
            ).with_for_update().execution_options(populate_existing=True)
        )
        if assignment is None:
            raise NotFoundError("Active profile assignment not found")

        policy = self.session.scalar(
            select(ProfilePolicy).where(
                ProfilePolicy.profile_id == profile_id
            ).with_for_update().execution_options(populate_existing=True)
        )
        if policy is None:
            raise ConflictError("Assigned profile has no access policy")

        selected_duration = duration or policy.default_duration
        requested = parse_duration(selected_duration)
        if requested > parse_duration(policy.maximum_duration):
            raise ConflictError("Requested duration exceeds the profile maximum")

        self._ensure_available(policy.lease_target, device.public_key, policy.networks)

        lease = self.add(UserLease(
            device_id=device_id,
            user_id=user_id,
            profile_user_id=assignment.id,
            ended_at=utcnow() + requested,
        ))
        self.session.add(LeaseProvisioning(
            lease_id=lease.id,
            document={
                "interface": policy.lease_target,
                "lease_id": str(lease.id),
                "device_id": str(device.id),
                "public_key": device.public_key,
                "addresses": list(policy.networks),
            },
            state="pending_apply",
        ))
        self.session.flush()
        return lease

    def revoke(self, lease: UserLease) -> UserLease:
        """Revoke idempotently, preserving the first revocation time.
        
        :param lease: The lease to revoke.
        :type lease: UserLease
        :return: The revoked lease.
        :rtype: UserLease
        """
        if lease.revoked_at is None:
            lease.revoked_at = utcnow()
        self.session.execute(
            update(LeaseProvisioning)
            .where(LeaseProvisioning.lease_id == lease.id, LeaseProvisioning.state != "deleted")
            .values(state="pending_delete")
        )
        return lease

    def revoke_matching(self, *conditions: ColumnElement[bool]) -> None:
        """Revoke leases affected by another domain operation.
        
        :param conditions: Conditions to match leases for revocation.
        :type conditions: ColumnElement[bool]
        """
        matching = select(UserLease.id).where(UserLease.revoked_at.is_(None), *conditions)
        self.session.execute(
            update(LeaseProvisioning)
            .where(LeaseProvisioning.lease_id.in_(matching), LeaseProvisioning.state != "deleted")
            .values(state="pending_delete")
        )
        self.session.execute(
            update(UserLease).where(UserLease.revoked_at.is_(None), *conditions)
            .values(revoked_at=utcnow())
        )
