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
from ipaddress import ip_interface, ip_network
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
    PeerAllocation,
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

    def _allocate_addresses(self, device_id: int, policy: ProfilePolicy) -> list[str]:
        pools = [ip_network(value) for value in policy.address_pools]
        allocation = self.session.get(PeerAllocation, (device_id, policy.lease_target))
        if allocation is not None:
            if not all(any(ip_interface(address).ip in pool for pool in pools)
                       for address in allocation.addresses):
                raise ConflictError("The device allocation is outside the configured address pools")
            if {ip_interface(address).version for address in allocation.addresses} != {
                pool.version for pool in pools
            }:
                raise ConflictError(
                    "The device allocation does not match the configured IP families"
                )
            return list(allocation.addresses)
        allocated = self.session.scalars(select(PeerAllocation).where(
            PeerAllocation.interface == policy.lease_target
        )).all()
        used = {ip_interface(address).ip for record in allocated for address in record.addresses}
        addresses: list[str] = []
        for pool in pools:
            hosts = pool.hosts()
            next(hosts, None)
            address = next((host for host in hosts if host not in used), None)
            if address is None:
                raise ConflictError("The WireGuard client address pool is exhausted")
            addresses.append(f"{address}/{address.max_prefixlen}")
        self.session.add(PeerAllocation(
            device_id=device_id, interface=policy.lease_target, addresses=addresses,
        ))
        self.session.flush()
        return addresses

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

        duplicate = self.session.scalar(select(UserLease.id).join(
            ProfileUser, ProfileUser.id == UserLease.profile_user_id
        ).join(LeaseProvisioning, LeaseProvisioning.lease_id == UserLease.id).where(
            UserLease.user_id == user_id,
            UserLease.device_id == device_id,
            ProfileUser.profile_id == profile_id,
            LeaseProvisioning.state != "deleted",
        ))
        if duplicate is not None:
            raise ConflictError(
                "The user and device already have a reserved lease for this profile"
            )
        addresses = self._allocate_addresses(device_id, policy)

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
                "addresses": addresses,
                "networks": list(policy.networks),
                "endpoint": policy.endpoint,
                "server_public_key": policy.public_key,
            },
            state="pending_apply",
        ))
        self.session.flush()
        return lease

    def client_configuration(self, lease: UserLease) -> dict[str, object]:
        """Return public client parameters for a usable lease and its shared peer.

        :param lease: An owned lease whose provisioning has completed.
        :returns: Parameters and a template requiring a locally supplied private key.
        :rtype: dict[str, object]
        :raises ConflictError: If the requested lease is not active.
        """
        if lease_status(lease) != "active":
            raise ConflictError("Client configuration requires an active provisioned lease")
        record = self.session.get(LeaseProvisioning, lease.id)
        if record is None:
            raise ConflictError("The lease has no WireGuard configuration")
        document = record.document
        records = self.session.scalars(select(LeaseProvisioning).join(
            UserLease, UserLease.id == LeaseProvisioning.lease_id
        ).where(
            UserLease.device_id == lease.device_id,
            UserLease.user_id == lease.user_id,
            UserLease.revoked_at.is_(None), UserLease.ended_at > utcnow(),
            LeaseProvisioning.state == "applied",
        )).all()
        shared = [item for item in records
                  if item.document.get("interface") == document["interface"]
                  and item.document.get("public_key") == document["public_key"]]
        networks = sorted({str(network) for item in shared
                           for network in cast(list[str], item.document["networks"])})
        addresses = cast(list[str], document["addresses"])
        template = (
            "[Interface]\nPrivateKey = REPLACE_WITH_LOCAL_PRIVATE_KEY\n"
            f"Address = {', '.join(addresses)}\n\n[Peer]\n"
            f"PublicKey = {document['server_public_key']}\n"
            f"Endpoint = {document['endpoint']}\n"
            f"AllowedIPs = {', '.join(networks)}\n"
        )
        return {
            "lease_id": lease.id, "interface": document["interface"],
            "device_public_key": document["public_key"],
            "server_public_key": document["server_public_key"],
            "endpoint": document["endpoint"], "addresses": addresses,
            "allowed_ips": networks, "active_lease_ids": sorted(item.lease_id for item in shared),
            "expires_at": lease.ended_at.isoformat() + "Z",
            "configuration_template": template,
        }

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
