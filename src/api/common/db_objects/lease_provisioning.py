"""Persist VPN provisioning requests and their immutable lease documents.

.. classes::
    - `LeaseProvisioning`: State shared by the API and scheduler.
    - `ProvisioningLock`: Serialize provisioning reservations.

.. module_author:: Rémi Verschuur <rverschuur@audit-io.fr>
.. version:: 1.0.0
"""
from __future__ import annotations

from sqlalchemy import ForeignKey, Integer, JSON, String
from sqlalchemy.orm import Mapped, mapped_column

from ._common import Base, TABLE_ARGS, foreign_key_target


class LeaseProvisioning(Base):
    """Store the desired operation and immutable WireGuard document.
    Store the desired operation and immutable WireGuard document.

    :param pending_apply: The request is waiting to be applied.
    :type pending_apply: str
    :param applied: The request has been successfully applied.
    :type applied: str
    :param pending_delete: The request is waiting to be deleted.
    :type pending_delete: str
    :param deleted: The request has been successfully deleted.
    :type deleted: str
    :param uncertain: The request is in an uncertain state due to an error.
    :type uncertain: str
    """

    __tablename__ = "lease_provisioning"
    __table_args__ = TABLE_ARGS

    lease_id: Mapped[int] = mapped_column(
        ForeignKey(foreign_key_target("leases")), primary_key=True
    )
    document: Mapped[dict[str, object]] = mapped_column(
        JSON,
        nullable=False,
        comment="Immutable VPN document",
    )
    state: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="pending_apply",
        comment="Current state of the provisioning request",
    )
    error: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
        comment="Error message if the provisioning failed",
    )


class ProvisioningLock(Base):
    """Store the shared transaction lock used for provisioning reservations.

    :param id: Identifier of the lock.
    :type id: int
    :param version: Version of the lock.
    :type version: int
    """

    __tablename__ = "provisioning_lock"
    __table_args__ = TABLE_ARGS

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        comment="Identifier of the lock",
    )
    version: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        comment="Version of the lock",
    )
