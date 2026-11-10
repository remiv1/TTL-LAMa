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
from datetime import datetime, timezone
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
from api.logging_config import log_event
from scheduler.ssh import format_subprocess_failure
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
            log_event(
                LOGGER,
                logging.WARNING,
                "provisioning.poll",
                "failed error=%s",
                type(error).__name__,
            )
            self.database.session.rollback()
        finally:
            self.database.session.remove()
            self._lock.release()

    def reconcile(self) -> None:
        """Converge backend peers and expiration jobs to persisted leases."""
        lease_states, desired = self._load_desired_state()
        observed = self._load_observed_state()
        self._reconcile_peers(desired, observed)
        self._restore_expiration_jobs(lease_states)
        self._persist_reconciliation(lease_states)
        log_event(
            LOGGER,
            logging.INFO,
            "reconciliation.run",
            "succeeded leases=%s active=%s",
            len(lease_states),
            len(desired),
        )

    def _load_desired_state(
        self,
    ) -> tuple[
        dict[int, tuple[bool, datetime]],
        dict[tuple[str, str], tuple[dict[str, object], tuple[str, ...]]],
    ]:
        session = self.database.session()
        now = utcnow()
        lease_states: dict[int, tuple[bool, datetime]] = {}
        desired: dict[tuple[str, str], tuple[dict[str, object], tuple[str, ...]]] = {}
        try:
            rows = session.execute(
                select(LeaseProvisioning, Lease)
                .join(Lease, Lease.id == LeaseProvisioning.lease_id)
                .order_by(LeaseProvisioning.lease_id)
            ).all()
            for record, lease in rows:
                document = dict(record.document)
                interface, identity, addresses = self._parse_peer_state(
                    document.get("interface"),
                    document.get("public_key"),
                    document.get("addresses"),
                    "Invalid persisted WireGuard lease document",
                )
                end = lease.ended_at
                if end.tzinfo is not None:
                    end = end.astimezone(timezone.utc).replace(tzinfo=None)
                active = lease.revoked_at is None and end > now
                lease_states[lease.id] = (active, lease.ended_at)
                if active:
                    key = (interface, identity)
                    if key in desired:
                        raise RuntimeError("Duplicate active WireGuard peer in database")
                    desired[key] = (document, addresses)
            session.rollback()
            return lease_states, desired
        finally:
            self.database.session.remove()

    def _load_observed_state(self) -> dict[tuple[str, str], tuple[str, ...]]:
        observed: dict[tuple[str, str], tuple[str, ...]] = {}
        for peer in self.backend.list_leases():
            interface, identity, addresses = self._parse_peer_state(
                peer.get("interface"),
                peer.get("identity"),
                peer.get("addresses"),
                "Invalid WireGuard peer state",
            )
            key = (interface, identity)
            if key in observed:
                raise RuntimeError("Duplicate WireGuard peer state")
            observed[key] = addresses
        return observed

    @staticmethod
    def _parse_peer_state(
        interface: object,
        identity: object,
        addresses: object,
        error_message: str,
    ) -> tuple[str, str, tuple[str, ...]]:
        if (
            not isinstance(interface, str)
            or not interface
            or not isinstance(identity, str)
            or not identity
            or not isinstance(addresses, list)
        ):
            raise RuntimeError(error_message)
        parsed_addresses: list[str] = []
        for address in cast(list[object], addresses):
            if not isinstance(address, str):
                raise RuntimeError(error_message)
            parsed_addresses.append(address)
        return interface, identity, tuple(parsed_addresses)

    def _reconcile_peers(
        self,
        desired: dict[tuple[str, str], tuple[dict[str, object], tuple[str, ...]]],
        observed: dict[tuple[str, str], tuple[str, ...]],
    ) -> None:
        for key, (document, desired_addresses) in desired.items():
            current_addresses = observed.pop(key, None)
            if current_addresses is None or set(current_addresses) != set(desired_addresses):
                self.backend.grant(json.dumps(document, separators=(",", ":")))

        for (interface, identity), addresses in observed.items():
            self.backend.revoke(json.dumps({
                "interface": interface,
                "public_key": identity,
                "addresses": list(addresses),
            }, separators=(",", ":")))

    def _restore_expiration_jobs(
        self,
        lease_states: dict[int, tuple[bool, datetime]],
    ) -> None:
        for lease_id, (active, ended_at) in lease_states.items():
            if not active:
                self._remove_expiration(lease_id)
                continue
            run_date = (
                ended_at.replace(tzinfo=timezone.utc)
                if ended_at.tzinfo is None
                else ended_at.astimezone(timezone.utc)
            )
            self.scheduler.add_job(
                self.expire,
                "date",
                run_date=run_date,
                args=[lease_id],
                id=f"lease-expiry-{lease_id}",
                misfire_grace_time=None,
                replace_existing=True,
            )

    def _persist_reconciliation(
        self,
        lease_states: dict[int, tuple[bool, datetime]],
    ) -> None:
        session = self.database.session()
        try:
            for lease_id, (active, _) in lease_states.items():
                session.execute(update(LeaseProvisioning).where(
                    LeaseProvisioning.lease_id == lease_id,
                ).values(state="applied" if active else "deleted", error=None))
            session.commit()
        finally:
            self.database.session.remove()

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
            if isinstance(error, subprocess.CalledProcessError):
                self._log_subprocess_failure(lease_id, applying, error)
            else:
                log_event(
                    LOGGER,
                    logging.WARNING,
                    f"lease.provisioning.{'apply' if applying else 'delete'}",
                    "failed lease_id=%s error=%s",
                    lease_id,
                    type(error).__name__,
                )
            self._fail(session, lease_id, applying)
            return
        if applying:
            self._complete_apply(session, lease_id)
        else:
            self._complete_delete(session, lease_id)

    @staticmethod
    def _log_subprocess_failure(
        lease_id: int,
        applying: bool,
        error: subprocess.CalledProcessError,
    ) -> None:
        operation = "apply" if applying else "delete"
        log_event(
            LOGGER,
            logging.WARNING,
            f"lease.provisioning.{operation}",
            "failed lease_id=%s %s",
            lease_id,
            format_subprocess_failure(error),
        )

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
            log_event(
                LOGGER,
                logging.WARNING,
                "lease.provisioning.apply",
                "superseded lease_id=%s; deletion scheduled",
                lease_id,
            )
        else:
            log_event(
                LOGGER,
                logging.INFO,
                "lease.provisioning.apply",
                "succeeded lease_id=%s",
                lease_id,
            )

    def _complete_delete(self, session: Session, lease_id: int) -> None:
        lease = session.get(Lease, lease_id)
        expired = False
        if lease is not None and lease.revoked_at is None:
            end = lease.ended_at
            if end.tzinfo is not None:
                end = end.astimezone(timezone.utc).replace(tzinfo=None)
            expired = end <= utcnow()
        session.execute(update(LeaseProvisioning).where(
            LeaseProvisioning.lease_id == lease_id,
            LeaseProvisioning.state == "deleting",
        ).values(state=case(
            (LeaseProvisioning.error == "apply_failed", "uncertain"),
            else_="deleted",
        )))
        session.commit()
        self._remove_expiration(lease_id)
        if expired:
            log_event(
                LOGGER,
                logging.INFO,
                "lease.expire",
                "succeeded lease_id=%s",
                lease_id,
            )
        log_event(
            LOGGER,
            logging.INFO,
            "lease.provisioning.delete",
            "succeeded access_removed lease_id=%s",
            lease_id,
        )

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
                result = cast(
                    CursorResult[object],
                    session.execute(update(LeaseProvisioning).where(
                        LeaseProvisioning.lease_id == lease_id,
                        LeaseProvisioning.state.not_in(("deleted", "uncertain")),
                    ).values(state="pending_delete"))
                )
                session.commit()
                if result.rowcount:
                    log_event(
                        LOGGER,
                        logging.INFO,
                        "lease.expire",
                        "deletion requested lease_id=%s",
                        lease_id,
                    )
            else:
                session.rollback()
        finally:
            self.database.session.remove()
