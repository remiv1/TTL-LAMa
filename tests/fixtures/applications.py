"""Application fixture for TTL-LAMa tests."""
from __future__ import annotations

import uuid
from collections.abc import Callable
from threading import Event, Lock
from typing import TYPE_CHECKING, Iterator, Protocol
from unittest.mock import Mock

import pytest

from apscheduler.schedulers.background import BackgroundScheduler
from flask import Flask, Blueprint
from flask_wtf.csrf import CSRFProtect
from sqlalchemy import func, select

from api.bootstrap import create_app
from api.common.db_objects.users import User as DatabaseUser
from api.common.db_objects.lease_provisioning import LeaseProvisioning
from api.config import FlaskSettings, DatabaseSettings
from api.v1 import api_v1, protect_cookie_authenticated_requests
from scheduler.leases import LeaseScheduler

if TYPE_CHECKING:
    from scheduler_types import ScheduledJobs

    class _TestScheduler(ScheduledJobs, Protocol):
        """Add test lifecycle operations to the shared scheduler protocol."""

        def pause(self) -> None: ... # pylint: disable=C0116

        def remove_job(self, job_id: str) -> None: ... # pylint: disable=C0116


def _start_test_scheduler(
    scheduler: _TestScheduler,
    process_requests: Callable[[], None],
) -> Callable[[], None]:
    callback_lock = Lock()
    stopping = Event()

    def process_requests_if_active() -> None:
        with callback_lock:
            if not stopping.is_set():
                process_requests()

    scheduler.add_job(
        process_requests_if_active,
        "interval",
        seconds=0.05,
        max_instances=1,
        id="test-lease-polling",
    )
    scheduler.start()

    def stop_polling() -> None:
        scheduler.pause()
        scheduler.remove_job("test-lease-polling")
        with callback_lock:
            stopping.set()

    return stop_polling


def _stop_test_scheduler(scheduler: _TestScheduler) -> None:
    scheduler.shutdown(wait=True)


@pytest.fixture
def running_lease_scheduler(app: Flask) -> Iterator[Mock]:  # pylint: disable=W0621
    """Run the scheduler with a simulated VPN backend."""
    scheduler = BackgroundScheduler()
    backend = Mock()
    database = app.extensions["database_config"]
    session = database.session()
    previous_id = session.scalar(select(func.max(LeaseProvisioning.lease_id))) or 0
    session.rollback()
    worker = LeaseScheduler(database, scheduler, backend)

    def process_test_requests() -> None:
        try:
            session = database.session()
            lease_ids = list(session.scalars(select(LeaseProvisioning.lease_id).where(
                LeaseProvisioning.lease_id > previous_id,
                LeaseProvisioning.state.in_(("pending_apply", "pending_delete", "uncertain")),
            )))
            session.rollback()
            for lease_id in lease_ids:
                worker.process(lease_id)
        finally:
            database.session.remove()

    stop_polling = _start_test_scheduler(scheduler, process_test_requests)
    try:
        yield backend
    finally:
        try:
            stop_polling()
        finally:
            _stop_test_scheduler(scheduler)

@pytest.fixture
def app(database_settings: DatabaseSettings) -> Iterator[Flask]:    # pylint: disable=W0621
    """Provide a Flask application configured for testing."""
    username = f"admin-{uuid.uuid4().hex[:12]}"
    settings = FlaskSettings.model_validate({
        "AUTH_MODE": "internal",
        "FLASK_ENV": "testing",
        "SECRET_KEY": "test-secret-key-with-more-than-thirty-two-characters",
        "ADMIN_USERNAME": username,
        "ADMIN_PASSWORD": "correct-horse-battery",
        "ENFORCE_SECURE_CONNECTION": False,
        "SESSION_COOKIE_SECURE": False,
    })
    application = create_app(settings, database_settings)
    application.config["TEST_ADMIN_USERNAME"] = username
    yield application
    database = application.extensions["database_config"]
    admin_id = database.session().scalar(
        select(DatabaseUser.id).where(DatabaseUser.username == username)
    )
    if admin_id is not None:
        application.extensions["auth_manager"].user_service.delete_user(admin_id)
    application.extensions["database_config"].close()

@pytest.fixture
def oidc_app(
    oidc_settings: FlaskSettings,
    database_settings: DatabaseSettings,
) -> Iterator[Flask]:
    """Provide a Flask application configured for OIDC testing."""
    application = create_app(oidc_settings, database_settings)
    yield application
    application.extensions["database_config"].close()

@pytest.fixture
def csrf_app() -> Flask:
    """Provide a Flask application configured for CSRF testing."""
    app = Flask(__name__)   # pylint: disable=W0621
    app.secret_key = "test-secret-key-with-more-than-thirty-two-characters"

    csrf = CSRFProtect(app)
    csrf.exempt(api_v1)

    test_api = Blueprint("test_api", __name__, url_prefix="/test")
    csrf.exempt(test_api)
    test_api.before_request(protect_cookie_authenticated_requests)

    @test_api.post("/mutate")
    def mutate():
        """Handle a POST request to mutate the resource."""
        return "", 204

    app.register_blueprint(api_v1)
    app.register_blueprint(test_api)
    return app
