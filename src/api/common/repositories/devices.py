"""Reusable device administration."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session
from sqlalchemy.sql.elements import ColumnElement

from api.common.db_objects.devices import Device
from api.common.db_objects.leases import Lease
from api.common.db_objects.profiles import ProfileUser
from .base import Repository
from .leases import LeaseRepository, utcnow


class DeviceRepository(Repository[Device]):
    """Manage device state and its dependent leases."""

    def __init__(self, session: Session) -> None:
        super().__init__(session, Device)

    def find(self, *, lease: int | None = None, profile: int | None = None) -> list[Device]:
        """Filter devices through their leases."""
        conditions: list[ColumnElement[bool]] = []
        if lease is not None:
            conditions.append(Device.id.in_(select(Lease.device_id).where(Lease.id == lease)))
        if profile is not None:
            conditions.append(Device.id.in_(
                select(Lease.device_id).join(ProfileUser)
                .where(ProfileUser.profile_id == profile)
            ))
        return self.list(*conditions)

    def update(self, device: Device, *, name: str | None = None,
               public_key: str | None = None) -> Device:
        """Update metadata, revoking leases when the VPN identity changes."""
        if name is not None:
            device.name = name
        if public_key is not None and public_key != device.public_key:
            LeaseRepository(self.session).revoke_matching(Lease.device_id == device.id)
            device.public_key = public_key
        return device

    def block(self, device: Device) -> Device:
        """Block a device and revoke its leases."""
        if device.revoked_at is None:
            device.revoked_at = utcnow()
        LeaseRepository(self.session).revoke_matching(Lease.device_id == device.id)
        return device
