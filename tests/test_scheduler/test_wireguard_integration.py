"""Exercise scheduler reconciliation through a real WireGuard SSH backend."""
from __future__ import annotations

import base64
import json
import os
import subprocess
import time
from collections.abc import Iterator
from datetime import timedelta
from ipaddress import IPv4Network
from pathlib import Path
from typing import TYPE_CHECKING, cast
from uuid import uuid4

import pytest
import yaml
from apscheduler.schedulers.background import BackgroundScheduler
from flask import Flask

from api.bootstrap import create_app
from api.common.db_objects.lease_provisioning import LeaseProvisioning
from api.common.db_objects.leases import Lease
from api.common.repositories import (
    DeviceRepository,
    LeaseRepository,
    ProfileRepository,
    UserRepository,
)
from api.config import DatabaseSettings, FlaskSettings
from api.common.repositories.leases import utcnow
from api.config.c_profiles import AccessProfile
from scheduler.leases import LeaseScheduler
from scheduler.panic import PanicMode, PanicSettings
from scheduler.ssh import SSHCommandExecutor
from scheduler.main import _reconcile_on_startup    # type: ignore
from vpn_backends.wireguard import WireGuardBackend

if TYPE_CHECKING:
    from scheduler_types import ScheduledJobs

pytestmark = pytest.mark.integration
SHARED_SSH_DIRECTORY = Path("/run/ttl-lama-test")


@pytest.fixture(scope="session")
def wireguard_executor(tmp_path_factory: pytest.TempPathFactory) -> Iterator[SSHCommandExecutor]:
    """Create an ephemeral client identity trusted by the backend container."""
    host = os.environ.get("TTL_LAMA_TEST_WIREGUARD_BACKEND")
    if not host:
        pytest.skip("The containerized WireGuard backend is not configured")

    key_directory = tmp_path_factory.mktemp("wireguard-ssh")
    identity_file = key_directory / "id_ed25519"
    subprocess.run(
        ["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-f", str(identity_file)],
        check=True,
        capture_output=True,
        text=True,
    )
    (SHARED_SSH_DIRECTORY / "authorized_keys").write_text(
        identity_file.with_suffix(".pub").read_text(encoding="utf-8"),
        encoding="utf-8",
    )

    known_hosts_file = key_directory / "known_hosts"
    known_hosts: str | None = None
    last_scan_error = "No SSH host key was returned"
    for attempt in range(5):
        key_scan = subprocess.run(
            ["ssh-keyscan", "-T", "5", "-t", "ed25519", host],
            check=False,
            capture_output=True,
            text=True,
        )
        if key_scan.returncode == 0 and key_scan.stdout.strip():
            known_hosts = key_scan.stdout
            break
        last_scan_error = key_scan.stderr.strip() or last_scan_error
        if attempt < 4:
            time.sleep(1)
    if known_hosts is None:
        raise RuntimeError(f"Unable to scan SSH host {host}: {last_scan_error}")
    known_hosts_file.write_text(known_hosts, encoding="utf-8")

    config_file = key_directory / "ssh_config.yml"
    config_file.write_text(yaml.safe_dump({
        "ssh_config": {
            "host": host,
            "port": 22,
            "user": "ttl-lama",
            "identity_file": str(identity_file),
            "known_hosts_file": str(known_hosts_file),
            "connection_timeout": 10,
        },
    }), encoding="utf-8")
    executor = SSHCommandExecutor(config_path=config_file, timeout=15)
    executor.run([
        "sudo", "-n", "ttlama", "backend", "wg", "leases", "ls",
        "--interface", "all", "--json",
    ])
    yield executor
    (SHARED_SSH_DIRECTORY / "authorized_keys").unlink(missing_ok=True)


@pytest.fixture(name="wireguard_app")
def create_wireguard_app(tmp_path: Path) -> Iterator[Flask]:
    """Provide an isolated SQLite application for the real-backend scenario."""
    settings = FlaskSettings.model_validate({
        "AUTH_MODE": "internal",
        "FLASK_ENV": "testing",
        "SECRET_KEY": "test-secret-key-with-more-than-thirty-two-characters",
        "ADMIN_USERNAME": f"admin-{uuid4().hex[:12]}",
        "ADMIN_PASSWORD": "correct-horse-battery",
        "ENFORCE_SECURE_CONNECTION": False,
        "SESSION_COOKIE_SECURE": False,
    })
    database_settings = DatabaseSettings(DB_PATH=str(tmp_path / "wireguard-integration.db"))
    application = create_app(settings, database_settings)
    try:
        yield application
    finally:
        application.extensions["database_config"].close()


def test_scheduler_reconciles_real_wireguard_backend(
    wireguard_app: Flask,
    wireguard_executor: SSHCommandExecutor, # pylint: disable=W0621
    request: pytest.FixtureRequest,
) -> None:
    """Startup reconciliation repairs drift and restores lease expiration."""
    database = wireguard_app.extensions["database_config"]
    session = database.session()
    suffix = uuid4().hex
    network_id = uuid4().int & 0xFFFF
    test_network = IPv4Network(f"10.{network_id >> 8}.{network_id & 0xFF}.0/24")
    user = UserRepository(session).create(username=f"wireguard-{suffix}")
    profile_repository = ProfileRepository(session)
    profile = profile_repository.create(
        f"wireguard-{suffix}",
        AccessProfile(
            default_duration="1h",
            maximum_duration="2h",
            lease_target="ttlama-test0",
            networks=[test_network],
        ),
    )
    profile_repository.assign(user, profile)
    public_key = base64.b64encode(os.urandom(32)).decode("ascii")
    device = DeviceRepository(session).create(str(user.id), "wireguard-device", public_key)
    lease = LeaseRepository(session).create(
        user_id=str(user.id), device_id=device.id, profile_id=profile.id,
    )
    lease_id = lease.id
    session.commit()

    backend = WireGuardBackend(executor=wireguard_executor)
    scheduler = cast("ScheduledJobs", BackgroundScheduler())
    worker = LeaseScheduler(database, scheduler, backend)
    assert _reconcile_on_startup(worker, PanicMode(PanicSettings(retry=3))) is True
    scheduler.start()
    request.addfinalizer(scheduler.shutdown)

    state = next(peer for peer in backend.list_leases() if peer["identity"] == public_key)
    assert state["interface"] == "ttlama-test0"
    assert state["addresses"] == [str(test_network)]
    assert scheduler.get_job(f"lease-expiry-{lease_id}") is not None

    provisioning = database.session().get(LeaseProvisioning, lease_id)
    divergent_document = dict(provisioning.document)
    divergent_network = IPv4Network((int(test_network.network_address) ^ (1 << 8), 24))
    divergent_document["addresses"] = [str(divergent_network)]
    backend.grant(json.dumps(divergent_document, separators=(",", ":")))
    worker.reconcile()
    state = next(peer for peer in backend.list_leases() if peer["identity"] == public_key)
    assert state["addresses"] == [str(test_network)]

    orphan_key = base64.b64encode(os.urandom(32)).decode("ascii")
    backend.grant(json.dumps({
        "interface": "ttlama-test0",
        "lease_id": "orphan",
        "device_id": "orphan",
        "public_key": orphan_key,
        "addresses": ["10.250.0.0/24"],
    }, separators=(",", ":")))
    worker.reconcile()
    assert not any(peer["identity"] == orphan_key for peer in backend.list_leases())

    session = database.session()
    session.get(Lease, lease_id).ended_at = utcnow() - timedelta(seconds=1)
    session.commit()
    worker.reconcile()

    assert not any(peer["identity"] == public_key for peer in backend.list_leases())
    assert scheduler.get_job(f"lease-expiry-{lease_id}") is None
    assert database.session().get(LeaseProvisioning, lease_id).state == "deleted"
