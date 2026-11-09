"""Exercise VPN lease provisioning and scheduled revocation."""
from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from ipaddress import IPv4Network
from pathlib import Path
from threading import Barrier
from unittest.mock import Mock
from uuid import uuid4

import pytest
from apscheduler.schedulers.background import BackgroundScheduler
from flask import Flask
from sqlalchemy import update
from sqlalchemy.orm import Session

from api.common.db_objects.lease_provisioning import LeaseProvisioning
from api.common.db_objects.leases import Lease
from api.common.repositories import (
    DeviceRepository,
    LeaseRepository,
    ProfileRepository,
    UserRepository,
)
from api.common.repositories.base import ConflictError
from api.common.repositories.leases import utcnow
from api.config.c_profiles import AccessProfile
from api.config.c_databases import Settings as DatabaseSettings
from scheduler.leases import LeaseScheduler
from scheduler.ssh import SSHCommandExecutor, SSHConfiguration
from vpn_backends.wireguard import WireGuardBackend


@pytest.fixture
def database_settings(tmp_path: Path) -> DatabaseSettings:
    """Use a separate SQLite database for each scheduler scenario."""
    return DatabaseSettings(DB_PATH=str(tmp_path / "scheduler.db"))


@pytest.fixture
def lease_setup(app: Flask) -> tuple[LeaseScheduler, Mock, int]:
    """Create an authorized lease and a scheduler with a simulated backend."""
    database = app.extensions["database_config"]
    session = database.session()
    suffix = uuid4().hex
    user = UserRepository(session).create(username=f"scheduler-{suffix}")
    profile_repository = ProfileRepository(session)
    profile = profile_repository.create(
        f"scheduler-{suffix}",
        AccessProfile(
            default_duration="1h", maximum_duration="2h", lease_target=f"wg-{suffix}",
            networks=[IPv4Network("10.123.0.0/24")],
        ),
    )
    profile_repository.assign(user, profile)
    device = DeviceRepository(session).create(str(user.id), "scheduler-device", f"key-{suffix}")
    lease = LeaseRepository(session).create(
        user_id=str(user.id), device_id=device.id, profile_id=profile.id,
    )
    lease_id = lease.id
    session.commit()
    backend = Mock()
    scheduler = BackgroundScheduler()
    return LeaseScheduler(database, scheduler, backend), backend, lease_id


def test_apply_schedules_expiration_and_expiry_removes_peer(
    app: Flask,
    lease_setup: tuple[LeaseScheduler, Mock, int], # pylint: disable=W0621
) -> None:
    """Application schedules expiration and the expired peer is removed."""
    worker, backend, lease_id = lease_setup
    worker.poll()
    document = json.loads(backend.grant.call_args.args[0])
    assert document["lease_id"] == str(lease_id)
    assert document["addresses"] == ["10.123.0.0/24"]
    expiration = worker.scheduler.get_job(f"lease-expiry-{lease_id}")
    assert expiration is not None
    assert expiration.misfire_grace_time is None
    session = app.extensions["database_config"].session()
    assert session.get(LeaseProvisioning, lease_id).state == "applied"
    session.get(Lease, lease_id).ended_at = utcnow() - timedelta(seconds=1)
    session.commit()
    worker.expire(lease_id)
    worker.poll()
    backend.revoke.assert_called_once()
    session = app.extensions["database_config"].session()
    assert session.get(LeaseProvisioning, lease_id).state == "deleted"


def test_reconcile_applies_missing_peer_and_restores_expiration(
    app: Flask,
    lease_setup: tuple[LeaseScheduler, Mock, int],  # pylint: disable=W0621
) -> None:
    """Reconciliation applies a missing active peer and schedules its expiry."""
    worker, backend, lease_id = lease_setup
    backend.list_leases.return_value = []

    worker.reconcile()

    document = json.loads(backend.grant.call_args.args[0])
    assert document["lease_id"] == str(lease_id)
    assert document["interface"].startswith("wg-")
    assert worker.scheduler.get_job(f"lease-expiry-{lease_id}") is not None
    session = app.extensions["database_config"].session()
    assert session.get(LeaseProvisioning, lease_id).state == "applied"


def test_early_revocation_uses_original_document(
    app: Flask,
    lease_setup: tuple[LeaseScheduler, Mock, int], # pylint: disable=W0621
) -> None:
    """Early revocation removes the peer using the snapshot applied earlier."""
    worker, backend, lease_id = lease_setup
    worker.poll()
    session = app.extensions["database_config"].session()
    lease = session.get(Lease, lease_id)
    lease.device.public_key = "changed-public-key"
    LeaseRepository(session).revoke(lease)
    session.commit()
    worker.poll()
    assert backend.revoke.call_args.args[0] == backend.grant.call_args.args[0]
    assert worker.scheduler.get_job(f"lease-expiry-{lease_id}") is None


def test_failed_apply_requests_compensation(
    app: Flask,
    lease_setup: tuple[LeaseScheduler, Mock, int], # pylint: disable=W0621
) -> None:
    """An SSH error revokes the bail and retains an uncertain reservation."""
    worker, backend, lease_id = lease_setup
    backend.grant.side_effect = OSError("SSH unavailable")
    worker.poll()
    session = app.extensions["database_config"].session()
    assert session.get(Lease, lease_id).revoked_at is not None
    record = session.get(LeaseProvisioning, lease_id)
    assert record.state == "pending_delete"
    assert record.error == "apply_failed"
    worker.poll()
    session = app.extensions["database_config"].session()
    assert session.get(LeaseProvisioning, lease_id).state == "uncertain"
    backend.revoke.assert_called_once()


def test_overlapping_active_lease_is_rejected(
    app: Flask,
    lease_setup: tuple[LeaseScheduler, Mock, int], # pylint: disable=W0621
) -> None:
    """The same interface and overlapping profile cannot reserve a second peer."""
    _, _, lease_id = lease_setup
    session = app.extensions["database_config"].session()
    lease = session.get(Lease, lease_id)
    other_device = DeviceRepository(session).create(str(lease.user_id), "second", "another-key")
    with pytest.raises(ConflictError):
        LeaseRepository(session).create(
            user_id=str(lease.user_id), device_id=other_device.id, profile_id=lease.profile.id,
        )
    session.rollback()


def test_revocation_during_apply_is_not_overwritten(
    app: Flask,
    lease_setup: tuple[LeaseScheduler, Mock, int], # pylint: disable=W0621
) -> None:
    """A concurrent revocation wins over a late successful apply response."""
    worker, backend, lease_id = lease_setup
    database = app.extensions["database_config"]

    def revoke_during_apply(_document: str) -> None:
        with Session(database.engine) as session:
            session.execute(update(Lease).where(Lease.id == lease_id).values(revoked_at=utcnow()))
            session.execute(update(LeaseProvisioning).where(
                LeaseProvisioning.lease_id == lease_id,
            ).values(state="pending_delete"))
            session.commit()

    backend.grant.side_effect = revoke_during_apply
    worker.poll()
    session = database.session()
    assert session.get(LeaseProvisioning, lease_id).state == "pending_delete"
    assert worker.scheduler.get_job(f"lease-expiry-{lease_id}") is None
    worker.poll()
    backend.revoke.assert_called_once()


def test_failed_delete_is_retried(
    app: Flask,
    lease_setup: tuple[LeaseScheduler, Mock, int], # pylint: disable=W0621
) -> None:
    """A failed deletion keeps its reservation and is retried."""
    worker, backend, lease_id = lease_setup
    worker.poll()
    session = app.extensions["database_config"].session()
    LeaseRepository(session).revoke(session.get(Lease, lease_id))
    session.commit()
    backend.revoke.side_effect = [OSError("SSH unavailable"), None]
    worker.poll()
    session = app.extensions["database_config"].session()
    record = session.get(LeaseProvisioning, lease_id)
    assert record.state == "pending_delete"
    assert record.error == "delete_failed"
    worker.poll()
    session = app.extensions["database_config"].session()
    assert session.get(LeaseProvisioning, lease_id).state == "deleted"
    assert backend.revoke.call_count == 2


def test_expiration_during_job_registration_requests_deletion(
    app: Flask,
    lease_setup: tuple[LeaseScheduler, Mock, int],  # pylint: disable=W0621
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An expired lease is deleted even if expiration races with job registration."""
    worker, backend, lease_id = lease_setup
    session = app.extensions["database_config"].session()
    add_job = worker.scheduler.add_job

    def expire_during_registration(*args: object, **kwargs: object) -> object:
        job = add_job(*args, **kwargs)  # type: ignore
        session.get(Lease, lease_id).ended_at = utcnow() - timedelta(seconds=1)
        session.flush()
        return job

    monkeypatch.setattr(worker.scheduler, "add_job", expire_during_registration)
    worker.poll()
    session = app.extensions["database_config"].session()
    assert session.get(LeaseProvisioning, lease_id).state == "pending_delete"
    assert worker.scheduler.get_job(f"lease-expiry-{lease_id}") is None
    worker.poll()
    backend.revoke.assert_called_once()


def test_failed_job_registration_compensates_apply(
    app: Flask,
    lease_setup: tuple[LeaseScheduler, Mock, int],  # pylint: disable=W0621
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A peer is not reported active without a scheduled expiration."""
    worker, backend, lease_id = lease_setup
    monkeypatch.setattr(
        worker.scheduler,
        "add_job",
        Mock(side_effect=RuntimeError("scheduler unavailable")),
    )
    worker.poll()
    session = app.extensions["database_config"].session()
    assert session.get(Lease, lease_id).revoked_at is not None
    assert session.get(LeaseProvisioning, lease_id).state == "pending_delete"
    worker.poll()
    backend.revoke.assert_called_once()


def test_delete_confirmation_preserves_concurrent_compensation(
    app: Flask,
    lease_setup: tuple[LeaseScheduler, Mock, int],  # pylint: disable=W0621
) -> None:
    """A late deletion cannot release a reservation marked uncertain concurrently."""
    worker, backend, lease_id = lease_setup
    database = app.extensions["database_config"]
    session = database.session()
    session.get(LeaseProvisioning, lease_id).state = "pending_delete"
    session.commit()

    def compensate_before_confirmation(_document: str) -> None:
        with Session(database.engine) as concurrent:
            concurrent.execute(update(LeaseProvisioning).where(
                LeaseProvisioning.lease_id == lease_id,
            ).values(state="pending_delete", error="apply_failed"))
            concurrent.commit()

    backend.revoke.side_effect = compensate_before_confirmation
    worker.poll()
    database.session.remove()
    record = database.session().get(LeaseProvisioning, lease_id)
    assert record.state == "pending_delete"
    assert record.error == "apply_failed"


def test_concurrent_reservations_cannot_overlap(
    app: Flask,
    lease_setup: tuple[LeaseScheduler, Mock, int],  # pylint: disable=W0621
) -> None:
    """Concurrent creations serialize their network reservations."""
    _, _, lease_id = lease_setup
    database = app.extensions["database_config"]
    session = database.session()
    lease = session.get(Lease, lease_id)
    user_id, device_id, profile_id = str(lease.user_id), lease.device_id, lease.profile.id
    second = DeviceRepository(session).create(user_id, "concurrent-device", "concurrent-key")
    second_id = second.id
    session.get(LeaseProvisioning, lease_id).state = "deleted"
    session.commit()
    database.session.remove()
    barrier = Barrier(2)

    def create(device: int) -> bool:
        with Session(database.engine) as transaction:
            barrier.wait(timeout=5)
            try:
                LeaseRepository(transaction).create(
                    user_id=user_id, device_id=device, profile_id=profile_id,
                )
                transaction.commit()
                return True
            except ConflictError:
                transaction.rollback()
                return False

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(create, [device_id, second_id]))
    assert sorted(results) == [False, True]


def test_wireguard_cli_sends_document_on_ssh_stdin(monkeypatch: pytest.MonkeyPatch) -> None:
    """The remote CLI receives its lease through stdin with host verification enabled."""
    settings = SSHConfiguration(
        host="vpn.example", port=22, user="ttlama", identity_file=Path("/key"),
        known_hosts_file=Path("/known_hosts"), connection_timeout=10,
    )
    command = Mock()
    command.return_value.stdout = '{"success": true}'
    def load_configuration(_executor: SSHCommandExecutor) -> SSHConfiguration:
        return settings

    monkeypatch.setattr(SSHCommandExecutor, "_load_configuration", load_configuration)
    monkeypatch.setattr("scheduler.ssh.subprocess.run", command)
    backend = WireGuardBackend(executor=SSHCommandExecutor(timeout=12))
    document = '{"public_key":"key","addresses":["10.123.0.0/24"]}'
    backend.grant(document)
    arguments = command.call_args.args[0]
    assert arguments[-1] == "sudo -n ttlama backend wg leases apply --lease -"
    assert "StrictHostKeyChecking=yes" in arguments
    assert "-T" in arguments
    assert document not in arguments[-1]
    assert command.call_args.kwargs["input"] == document
    assert command.call_args.kwargs["timeout"] == 12
