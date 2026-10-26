"""Common fixtures and utilities for tests."""
from __future__ import annotations

import pytest
from flask import Flask

@pytest.fixture
def login_admin(app: Flask) -> tuple[str, str]: # pylint: disable=W0621
    """Provide the login credentials for the admin user."""
    return app.config["TEST_ADMIN_USERNAME"], "correct-horse-battery"   # type: ignore
