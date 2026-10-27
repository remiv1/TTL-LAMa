"""Application fixture for TTL-LAMa tests."""

import uuid
from typing import Iterator

import pytest

from flask import Flask, Blueprint
from flask_wtf.csrf import CSRFProtect
from sqlalchemy import select

from api.bootstrap import create_app
from api.common.db_objects.users import User as DatabaseUser
from api.config import FlaskSettings, DatabaseSettings
from api.v1 import api_v1, protect_cookie_authenticated_requests

@pytest.fixture
def app(database_settings: DatabaseSettings) -> Iterator[Flask]:    # pylint: disable=W0621
    """Provide a Flask application configured for testing."""
    username = f"admin-{uuid.uuid4().hex[:12]}"
    settings = FlaskSettings(
        AUTH_MODE="internal",
        FLASK_ENV="testing",
        SECRET_KEY="test-secret-key-with-more-than-thirty-two-characters",
        ADMIN_USERNAME=username,
        ADMIN_PASSWORD="correct-horse-battery",
        ENFORCE_SECURE_CONNECTION=False,
        SESSION_COOKIE_SECURE=False,
    )
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
