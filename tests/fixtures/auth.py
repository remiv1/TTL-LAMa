"""Authentication fixtures for tests."""

import pytest

from api.config import FlaskSettings

@pytest.fixture
def oidc_settings() -> FlaskSettings:
    """Provide OIDC settings for tests."""
    return FlaskSettings(
        AUTH_MODE="external",
        FLASK_ENV="testing",
        SECRET_KEY="test-secret-key-with-more-than-thirty-two-characters",
        OIDC_ISSUER="http://dex:5556/dex",
        OIDC_CLIENT_ID="ttl-lama-dex",
        OIDC_CLIENT_SECRET="ttl-lama-test-secret",
        OIDC_REDIRECT_URI='http://127.0.0.1:5555/auth/callback',
        ENFORCE_SECURE_CONNECTION=False,
        SESSION_COOKIE_SECURE=False,
    )
