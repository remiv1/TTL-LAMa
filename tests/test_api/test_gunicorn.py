"""Tests for database initialization before Gunicorn workers start."""

import runpy
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import Mock

import pytest
from flask import Flask
from sqlalchemy import select

from api import config
from api.config import DatabaseConfig


@pytest.fixture(name="gunicorn_settings")
def load_gunicorn_settings(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    """Load the production Gunicorn configuration without deployment secrets."""
    monkeypatch.setattr(
        config,
        "FlaskSettings",
        Mock(return_value=SimpleNamespace(
            SERVER_HOST="127.0.0.1",
            SERVER_PORT=8000,
            LOG_LEVEL="info",
        )),
    )
    configuration = Path(__file__).resolve().parents[2] / "src" / "gunicorn_conf.py"
    return runpy.run_path(str(configuration))


def test_application_is_preloaded_before_workers(
    gunicorn_settings: dict[str, Any],
) -> None:
    """The master must initialize the application before forking any worker."""
    assert gunicorn_settings["preload_app"] is True
    assert gunicorn_settings["workers"] > 1


def test_master_releases_database_before_forking(
    gunicorn_settings: dict[str, Any],
) -> None:
    """The initialized application's database is closed by the master hook."""
    database = Mock()
    application = SimpleNamespace(extensions={"database_config": database})
    server = SimpleNamespace(app=SimpleNamespace(wsgi=Mock(return_value=application)))

    gunicorn_settings["when_ready"](server)

    server.app.wsgi.assert_called_once_with()
    database.close.assert_called_once_with()


def test_database_reconnects_without_reinitializing(
    app: Flask,
    gunicorn_settings: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Workers can use the initialized database with a fresh session and pool."""
    database = app.extensions["database_config"]
    original_session = database.session()
    original_pool = database.engine.pool
    initialize = Mock(side_effect=AssertionError("Workers must not initialize tables"))
    monkeypatch.setattr(DatabaseConfig, "initialize", initialize)
    server = SimpleNamespace(app=SimpleNamespace(wsgi=Mock(return_value=app)))

    gunicorn_settings["when_ready"](server)

    assert database.engine.pool is not original_pool
    assert database.session() is not original_session
    assert database.session().scalar(select(1)) == 1
    assert app.test_client().get("/api/v1/csrf").status_code == 200
    initialize.assert_not_called()
