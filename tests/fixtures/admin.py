"""Administrative domain fixture for testing."""

from uuid import uuid4
from datetime import timedelta

import pytest
from flask import Flask

from api.common.db_objects.devices import Device
from api.common.db_objects.leases import Lease
from api.common.db_objects.users import User
from api.common.repositories import ProfileRepository, UserRepository
from api.common.repositories.leases import utcnow
from api.config.c_profiles import AccessProfile

from tests.test_api.test_admin import Domain, POLICY

@pytest.fixture
def domain(app: Flask) -> Domain:
    """Seed an isolated set of records using the public repository contract."""
    database = app.extensions["database_config"]
    session = database.session()
    user = UserRepository(session).add(User(
        username=f"user-{uuid4().hex}", enabled=True, is_admin=False,
    ))
    profiles = ProfileRepository(session)
    profile = profiles.create(f"profile-{uuid4().hex}", AccessProfile.model_validate(POLICY))
    assignment = profiles.assign(user, profile)
    device = Device(user_id=str(user.id), name="laptop", public_key="public-key")
    session.add(device)
    session.flush()
    lease = Lease(
        device_id=device.id, user_id=str(user.id), profile_user_id=assignment.id,
        ended_at=utcnow() + timedelta(hours=1),
    )
    expired = Lease(
        device_id=device.id, user_id=str(user.id), profile_user_id=assignment.id,
        ended_at=utcnow() - timedelta(hours=1),
    )
    session.add_all([lease, expired])
    session.commit()
    manager = app.extensions["auth_manager"]
    admin = manager.user_service.get_by_username(app.config["TEST_ADMIN_USERNAME"])
    admin_token = manager.session_service.create(str(admin.id))
    user_token = manager.session_service.create(str(user.id))
    return Domain(
        app, app.test_client(), {"Authorization": f"Bearer {admin_token}"},
        {"Authorization": f"Bearer {user_token}"},
        str(user.id), profile.id, device.id, lease.id, expired.id,
    )
