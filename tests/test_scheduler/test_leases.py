"""Exercise VPN lease provisioning and scheduled revocation."""
from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from ipaddress import IPv4Network, IPv6Network
from pathlib import Path
from threading import Barrier
from unittest.mock import Mock
from uuid import uuid4

import pytest
from apscheduler.schedulers.background import BackgroundScheduler
from flask import Flask
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from api.common.db_objects.lease_provisioning import LeaseProvisioning, PeerAllocation
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


@pytest.fixture(name="lease_setup")
def lease_context(app: Flask) -> tuple[LeaseScheduler, Mock, int]:
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
            endpoint="vpn.example.test:51820", public_key="server-key",
            address_pools=[IPv4Network("10.250.0.0/24")],
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
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Application schedules expiration and the expired peer is removed."""
    caplog.set_level("INFO")
    worker, backend, lease_id = lease_setup
    worker.poll()
    document = json.loads(backend.grant.call_args.args[0])
    assert document["lease_id"] == str(lease_id)
    assert document["addresses"] == ["10.250.0.2/32"]
    assert document["networks"] == ["10.123.0.0/24"]
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
    assert any(
        getattr(record, "operation", None) == "lease.expire"
        and "succeeded" in record.getMessage()
        for record in caplog.records
    )


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


def test_reconcile_after_expiration_removes_peer_without_restoring_job(
    app: Flask,
    lease_setup: tuple[LeaseScheduler, Mock, int],  # pylint: disable=W0621
) -> None:
    """A restarted scheduler removes an expired peer and does not restore its job."""
    worker, backend, lease_id = lease_setup
    session = app.extensions["database_config"].session()
    lease = session.get(Lease, lease_id)
    lease.ended_at = utcnow() - timedelta(seconds=1)
    session.commit()
    document = session.get(LeaseProvisioning, lease_id).document
    backend.list_leases.return_value = [{
        "interface": document["interface"],
        "identity": document["public_key"],
        "addresses": document["addresses"],
    }]

    worker.reconcile()

    backend.grant.assert_not_called()
    backend.revoke.assert_called_once()
    assert worker.scheduler.get_job(f"lease-expiry-{lease_id}") is None
    session = app.extensions["database_config"].session()
    assert session.get(LeaseProvisioning, lease_id).state == "deleted"


def test_reconcile_recovers_uncertain_active_lease(
    app: Flask,
    lease_setup: tuple[LeaseScheduler, Mock, int],  # pylint: disable=W0621
) -> None:
    """Startup reconciliation reapplies an active lease with uncertain provisioning."""
    worker, backend, lease_id = lease_setup
    session = app.extensions["database_config"].session()
    record = session.get(LeaseProvisioning, lease_id)
    record.state = "uncertain"
    record.error = "apply_failed"
    session.commit()
    backend.list_leases.return_value = []

    worker.reconcile()

    backend.grant.assert_called_once()
    assert worker.scheduler.get_job(f"lease-expiry-{lease_id}") is not None
    session = app.extensions["database_config"].session()
    record = session.get(LeaseProvisioning, lease_id)
    assert record.state == "applied"
    assert record.error is None


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
    caplog: pytest.LogCaptureFixture,
) -> None:
    """An SSH error revokes the bail and retains an uncertain reservation."""
    worker, backend, lease_id = lease_setup
    secret = "scheduler-error-secret-sentinel"
    backend.grant.side_effect = OSError(secret)
    caplog.set_level("WARNING")
    worker.poll()
    session = app.extensions["database_config"].session()
    assert session.get(Lease, lease_id).revoked_at is not None
    record = session.get(LeaseProvisioning, lease_id)
    assert record.state == "pending_delete"
    assert record.error == "apply_failed"
    assert any(
        getattr(entry, "operation", None) == "lease.provisioning.apply"
        and "failed" in entry.getMessage()
        for entry in caplog.records
    )
    assert secret not in " ".join(entry.getMessage() for entry in caplog.records)
    worker.poll()
    session = app.extensions["database_config"].session()
    assert session.get(LeaseProvisioning, lease_id).state == "uncertain"
    backend.revoke.assert_called_once()


def test_shared_destinations_allocate_distinct_client_addresses(
    app: Flask,
    lease_setup: tuple[LeaseScheduler, Mock, int], # pylint: disable=W0621
) -> None:
    """Two devices can use the same destinations without sharing client addresses."""
    _, _, lease_id = lease_setup
    session = app.extensions["database_config"].session()
    lease = session.get(Lease, lease_id)
    other_device = DeviceRepository(session).create(str(lease.user_id), "second", "another-key")
    second = LeaseRepository(session).create(
        user_id=str(lease.user_id), device_id=other_device.id, profile_id=lease.profile.id,
    )
    first_document = session.get(LeaseProvisioning, lease_id).document
    second_document = session.get(LeaseProvisioning, second.id).document
    assert first_document["networks"] == second_document["networks"]
    assert first_document["addresses"] != second_document["addresses"]
    session.rollback()


def test_shared_peer_survives_until_the_last_profile_lease_ends(
    app: Flask,
    lease_setup: tuple[LeaseScheduler, Mock, int],  # pylint: disable=W0621
) -> None:
    """Partial revocation preserves the peer without running a firewall operation."""
    worker, backend, lease_id = lease_setup
    database = app.extensions["database_config"]
    session = database.session()
    first = session.get(Lease, lease_id)
    profiles = ProfileRepository(session)
    policy = profiles.policy(first.profile)
    assert policy is not None
    second_profile = profiles.create("second-profile", policy.model_copy(update={
        "networks": [IPv4Network("10.20.0.0/24")],
    }))
    profiles.assign(first.user, second_profile)
    second = LeaseRepository(session).create(
        user_id=str(first.user_id), device_id=first.device_id, profile_id=second_profile.id,
    )
    second_id = second.id
    assert session.get(LeaseProvisioning, lease_id).document["addresses"] == session.get(
        LeaseProvisioning, second_id
    ).document["addresses"]
    with pytest.raises(ConflictError, match="reserved lease"):
        LeaseRepository(session).create(
            user_id=str(first.user_id), device_id=first.device_id, profile_id=first.profile.id,
        )
    session.commit()
    worker.poll()
    backend.list_leases.return_value = []
    worker.reconcile()
    session = database.session()
    first = session.get(Lease, lease_id)
    token = app.extensions["auth_manager"].session_service.create(str(first.user_id))
    headers = {"Authorization": f"Bearer {token}"}
    configuration_url = f"/api/v1/users/me/leases/{lease_id}/configuration"
    response = app.test_client().get(configuration_url, headers=headers)
    assert response.status_code == 200
    assert response.headers["Cache-Control"] == "no-store"
    payload = response.get_json()
    assert isinstance(payload, dict)
    assert payload["allowed_ips"] == ["10.123.0.0/24", "10.20.0.0/24"]
    assert payload["active_lease_ids"] == [lease_id, second_id]
    assert "REPLACE_WITH_LOCAL_PRIVATE_KEY" in payload["configuration_template"]
    assert app.test_client().get(configuration_url).status_code == 401
    session = database.session()
    LeaseRepository(session).revoke(session.get(Lease, lease_id))
    session.commit()
    worker.poll()
    backend.revoke.assert_not_called()
    assert app.test_client().get(configuration_url, headers=headers).status_code == 409
    session = database.session()
    assert session.get(LeaseProvisioning, second_id).state == "applied"
    LeaseRepository(session).revoke(session.get(Lease, second_id))
    session.commit()
    worker.poll()
    backend.revoke.assert_called_once()
    assert {call[0] for call in backend.method_calls} <= {"grant", "revoke", "list_leases"}


@pytest.mark.parametrize("dual_stack", [False, True])
def test_persistent_ipv6_allocation_and_pool_exhaustion(
    app: Flask, lease_setup: tuple[LeaseScheduler, Mock, int], dual_stack: bool, # pylint: disable=W0621
) -> None:
    """Reserve the router address and keep unique host addresses in each IP family."""
    _, _, lease_id = lease_setup
    database = app.extensions["database_config"]
    session = database.session()
    initial = session.get(Lease, lease_id)
    profiles = ProfileRepository(session)
    policy = profiles.policy(initial.profile)
    assert policy is not None
    pools: list[IPv4Network | IPv6Network] = [IPv6Network("fd42:250::/126")]
    if dual_stack:
        pools.insert(0, IPv4Network("10.251.0.0/30"))
    configured = policy.model_copy(update={
        "lease_target": "wg-dual", "address_pools": pools,
        "networks": [IPv4Network("10.20.0.0/24"), IPv6Network("fd42:20::/64")],
    })
    profile = profiles.create("dual-stack", configured)
    profiles.assign(initial.user, profile)
    lease = LeaseRepository(session).create(
        user_id=str(initial.user_id), device_id=initial.device_id, profile_id=profile.id,
    )
    first_addresses = session.get(LeaseProvisioning, lease.id).document["addresses"]
    assert first_addresses == (["10.251.0.2/32"] if dual_stack else []) + ["fd42:250::2/128"]
    session.get(LeaseProvisioning, lease.id).state = "deleted"
    lease.revoked_at = utcnow()
    session.flush()
    repeated = LeaseRepository(session).create(
        user_id=str(initial.user_id), device_id=initial.device_id, profile_id=profile.id,
    )
    assert session.get(LeaseProvisioning, repeated.id).document["addresses"] == first_addresses
    other = DeviceRepository(session).create(str(initial.user_id), "pool-device", "pool-key")
    if not dual_stack:
        LeaseRepository(session).create(
            user_id=str(initial.user_id), device_id=other.id, profile_id=profile.id,
        )
        other = DeviceRepository(session).create(str(initial.user_id), "full-pool", "full-key")
    with pytest.raises(ConflictError, match="exhausted"):
        LeaseRepository(session).create(
            user_id=str(initial.user_id), device_id=other.id, profile_id=profile.id,
        )
    session.rollback()


def test_client_configuration_is_scoped_to_the_owner_and_provisioning(
    app: Flask, lease_setup: tuple[LeaseScheduler, Mock, int], # pylint: disable=W0621
) -> None:
    """Reject another owner, pending provisioning and expired configurations."""
    worker, _, lease_id = lease_setup
    database = app.extensions["database_config"]
    session = database.session()
    lease = session.get(Lease, lease_id)
    owner_id = str(lease.user_id)
    other = UserRepository(session).create(username="configuration-other-owner")
    other_id = str(other.id)
    session.commit()
    manager = app.extensions["auth_manager"]
    owner_headers = {"Authorization": f"Bearer {manager.session_service.create(owner_id)}"}
    other_headers = {"Authorization": f"Bearer {manager.session_service.create(other_id)}"}
    url = f"/api/v1/users/me/leases/{lease_id}/configuration"
    client = app.test_client()
    assert client.get(url, headers=other_headers).status_code == 404
    assert client.get(url, headers=owner_headers).status_code == 409
    worker.poll()
    assert client.get(url, headers=owner_headers).status_code == 200
    session = database.session()
    session.get(Lease, lease_id).ended_at = utcnow() - timedelta(seconds=1)
    session.commit()
    assert client.get(url, headers=owner_headers).status_code == 409


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
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A failed deletion keeps its reservation and is retried."""
    caplog.set_level("INFO")
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
    assert any(
        getattr(entry, "operation", None) == "lease.provisioning.delete"
        and "failed" in entry.getMessage()
        for entry in caplog.records
    )
    worker.poll()
    session = app.extensions["database_config"].session()
    assert session.get(LeaseProvisioning, lease_id).state == "deleted"
    assert backend.revoke.call_count == 2
    assert any(
        getattr(entry, "operation", None) == "lease.provisioning.delete"
        and "succeeded" in entry.getMessage()
        for entry in caplog.records
    )


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
    """Concurrent devices receive distinct allocations for identical destinations."""
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
    assert results == [True, True]
    database.session.remove()
    session = database.session()
    allocations = session.scalars(select(PeerAllocation).where(
        PeerAllocation.device_id.in_((device_id, second_id))
    )).all()
    assert len(allocations) == 2
    assert allocations[0].addresses != allocations[1].addresses


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
