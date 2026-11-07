"""Apply and expire persisted VPN leases from the scheduler process.

.. classes::
    - `LeaseScheduler`: Dispatch provisioning and expiration work.

.. module_author:: Rémi Verschuur <rverschuur@audit-io.fr>
.. version:: 1.0.0
"""
from __future__ import annotations

import json
import logging
import subprocess
from datetime import timezone
from threading import Lock
from typing import TYPE_CHECKING, cast

from sqlalchemy import case, select, update
from sqlalchemy.engine import CursorResult
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from api.common.db_objects.lease_provisioning import LeaseProvisioning
from api.common.db_objects.leases import Lease
from api.common.repositories.leases import utcnow
from api.config.c_databases import DatabaseConfig
from vpn_backends.wireguard import WireGuardBackend

LOGGER = logging.getLogger(__name__)

if TYPE_CHECKING:
    from scheduler_types import ScheduledJobs


class LeaseScheduler:
    """Dispatch lease requests through one scheduler-owned backend.

    :param database: Shared database configuration.
    :type database: DatabaseConfig
    :param scheduler: Scheduler used for expiration jobs.
    :type scheduler: scheduler_types.ScheduledJobs
    :param backend: Optional backend transport.
    :type backend: WireGuardBackend | None
    """

    def __init__(
        self,
        database: DatabaseConfig,
        scheduler: ScheduledJobs,
        backend: WireGuardBackend | None = None,
    ) -> None:
        self.database = database
        self.scheduler = scheduler
        self.backend = backend or WireGuardBackend()
        self._lock = Lock()

    def poll(self) -> None:
        """Process pending provisioning and revocation requests sequentially."""
        if not self._lock.acquire(blocking=False):
            return
        try:
            session = self.database.session()
            requests = list(session.scalars(select(LeaseProvisioning.lease_id).where(
                LeaseProvisioning.state.in_(("pending_apply", "pending_delete", "uncertain"))
            ).order_by(LeaseProvisioning.lease_id)))
            session.rollback()
            for lease_id in requests:
                self.process(lease_id)
        except (SQLAlchemyError, OSError, RuntimeError, TypeError, ValueError) as error:
            LOGGER.warning("Unable to process VPN provisioning requests (%s)", type(error).__name__)
            self.database.session.rollback()
        finally:
            self.database.session.remove()
            self._lock.release()

    def process(self, lease_id: int) -> None:
        """Process a pending VPN operation for one lease.

        :param lease_id: Identifier of the lease to process.
        :type lease_id: int
        """
        session = self.database.session()
        claimed = self._claim(session, lease_id)
        if claimed is None:
            return
        document, applying = claimed
        try:
            if applying:
                self.backend.grant(document)
            else:
                self.backend.revoke(document)
        except (OSError, RuntimeError, ValueError, subprocess.SubprocessError) as error:
            LOGGER.warning("VPN operation failed for lease %s (%s)", lease_id, type(error).__name__)
            self._fail(session, lease_id, applying)
            return
        if applying:
            self._complete_apply(session, lease_id)
        else:
            self._complete_delete(session, lease_id)

    def _claim(self, session: Session, lease_id: int) -> tuple[str, bool] | None:
        record = session.get(LeaseProvisioning, lease_id)
        lease = session.get(Lease, lease_id)
        if record is None or lease is None:
            session.rollback()
            return None
        state = record.state
        if state not in ("pending_apply", "pending_delete", "uncertain"):
            session.rollback()
            return None
        document = json.dumps(record.document, separators=(",", ":"))
        applying = (
            state == "pending_apply"
            and lease.revoked_at is None
            and lease.ended_at > utcnow()
        )
        claimed = "applying" if applying else "deleting"
        result = cast(CursorResult[object], session.execute(update(LeaseProvisioning).where(
            LeaseProvisioning.lease_id == lease_id,
            LeaseProvisioning.state == state,
        ).values(state=claimed)))
        if result.rowcount != 1:
            session.rollback()
            return None
        session.commit()
        return document, applying

    def _fail(self, session: Session, lease_id: int, applying: bool) -> None:
        session.expire_all()
        record = session.get(LeaseProvisioning, lease_id)
        lease = session.get(Lease, lease_id)
        if record is None or lease is None:
            session.rollback()
            return
        if applying:
            record.error = "apply_failed"
            if lease.revoked_at is None:
                lease.revoked_at = utcnow()
        elif record.error != "apply_failed":
            record.error = "delete_failed"
        record.state = "pending_delete"
        session.commit()

    def _complete_apply(self, session: Session, lease_id: int) -> None:
        session.expire_all()
        record = session.get(LeaseProvisioning, lease_id)
        lease = session.get(Lease, lease_id)
        if record is None or lease is None:
            session.rollback()
            return
        if record.state != "applying" or lease.revoked_at is not None or lease.ended_at <= utcnow():
            session.execute(update(LeaseProvisioning).where(
                LeaseProvisioning.lease_id == lease_id,
                LeaseProvisioning.state == "applying",
            ).values(state="pending_delete"))
            session.commit()
            return
        scheduled = False
        try:
            self.scheduler.add_job(
                self.expire, "date", run_date=lease.ended_at.replace(tzinfo=timezone.utc),
                args=[lease_id], id=f"lease-expiry-{lease_id}", misfire_grace_time=None,
                replace_existing=True,
            )
            scheduled = True
        finally:
            if not scheduled:
                self._fail(session, lease_id, True)
        result = cast(CursorResult[object], session.execute(update(LeaseProvisioning).where(
            LeaseProvisioning.lease_id == lease_id,
            LeaseProvisioning.state == "applying",
            LeaseProvisioning.lease_id.in_(select(Lease.id).where(
                Lease.id == lease_id,
                Lease.revoked_at.is_(None),
                Lease.ended_at > utcnow(),
            )),
        ).values(state="applied")))
        if result.rowcount != 1:
            session.execute(update(LeaseProvisioning).where(
                LeaseProvisioning.lease_id == lease_id,
                LeaseProvisioning.state == "applying",
            ).values(state="pending_delete"))
        session.commit()
        if result.rowcount != 1:
            self._remove_expiration(lease_id)

    def _complete_delete(self, session: Session, lease_id: int) -> None:
        session.execute(update(LeaseProvisioning).where(
            LeaseProvisioning.lease_id == lease_id,
            LeaseProvisioning.state == "deleting",
        ).values(state=case(
            (LeaseProvisioning.error == "apply_failed", "uncertain"),
            else_="deleted",
        )))
        session.commit()
        self._remove_expiration(lease_id)

    def _remove_expiration(self, lease_id: int) -> None:
        job = self.scheduler.get_job(f"lease-expiry-{lease_id}")
        if job is not None:
            job.remove()

    def expire(self, lease_id: int) -> None:
        """Request removal of a lease whose persisted deadline has elapsed.

        :param lease_id: Identifier of the lease to inspect.
        :type lease_id: int
        """
        try:
            session = self.database.session()
            lease = session.get(Lease, lease_id)
            if lease is not None and (lease.revoked_at is not None or lease.ended_at <= utcnow()):
                session.execute(update(LeaseProvisioning).where(
                    LeaseProvisioning.lease_id == lease_id,
                    LeaseProvisioning.state.not_in(("deleted", "uncertain")),
                ).values(state="pending_delete"))
                session.commit()
            else:
                session.rollback()
        finally:
            self.database.session.remove()
