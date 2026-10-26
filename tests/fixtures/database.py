"""Database fixture for TTL-LAMa tests.

Provides database settings for different database engines based on environment variables.
"""
import os
import uuid
from typing import Iterator

import pytest
from flask import Flask
from sqlalchemy import select

from api.bootstrap import create_app
from api.common.db_objects.users import User as DatabaseUser
from api.config import FlaskSettings, DatabaseSettings
from api.config.c_databases import DbType

_DATABASE_URL_ENV = {
    "postgresql": "TTL_LAMA_TEST_POSTGRESQL_URL",
    "mariadb": "TTL_LAMA_TEST_MARIADB_URL",
    "mysql": "TTL_LAMA_TEST_MYSQL_URL",
}


def _database_cases() -> list[tuple[str, str | None]]:
    requested = os.environ.get("TTL_LAMA_TEST_DATABASES", "sqlite")
    cases: list[tuple[str, str | None]] = []
    for name in requested.split(","):
        name = name.strip().lower()
        if name == "sqlite":
            cases.append((name, None))
            continue
        env_name = _DATABASE_URL_ENV.get(name)
        if env_name is None:
            raise ValueError(f"Moteur de test inconnu : {name}")
        url = os.environ.get(env_name)
        if not url:
            raise ValueError(f"La variable {env_name} est requise pour tester {name}")
        cases.append((name, url))
    if not cases:
        raise ValueError("Au moins un moteur de base de données doit être testé")
    return cases


@pytest.fixture(
    scope="session",
    params=_database_cases(),
    ids=lambda case: case[0],
)
def database_settings(
    request: pytest.FixtureRequest,
    tmp_path_factory: pytest.TempPathFactory,
) -> Iterator[DatabaseSettings]:
    """Provide database settings for tests based on the requested database engine."""
    engine_name, raw_url = request.param
    if engine_name == "sqlite":
        database_path = tmp_path_factory.mktemp("ttl-lama-sqlite") / "test.db"
        yield DatabaseSettings(DB_PATH=str(database_path))
        return

    from sqlalchemy.engine import make_url  # pylint: disable=C0415

    database_url = make_url(raw_url)
    if engine_name == "postgresql":
        yield DatabaseSettings(
            DB_TYPE=DbType.POSTGRESQL,
            DB_HOST=database_url.host or "",
            DB_PORT=database_url.port or 0,
            DB_USER=database_url.username or "",
            DB_PASSWORD=database_url.password or "",
            DB_NAME=database_url.database or "",
        )
        return

    driver_type = DbType.MARIADB if engine_name == "mariadb" else DbType.MYSQL
    yield DatabaseSettings(
        DB_TYPE=driver_type,
        DB_HOST=database_url.host or "",
        DB_PORT=database_url.port or 0,
        DB_USER=database_url.username or "",
        DB_PASSWORD=database_url.password or "",
        DB_NAME=database_url.database or "",
    )

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
        application.extensions["auth_manager"].users.delete_user(admin_id)
    application.extensions["database_config"].close()
