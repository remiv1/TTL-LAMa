"""Tests de la configuration du hasher de mots de passe."""

from pathlib import Path

import pytest
from argon2 import PasswordHasher, extract_parameters

from api.bootstrap import create_app
from api.config import DatabaseSettings, FlaskSettings
from api.config.c_password_hasher import Settings as PasswordHasherSettings
from api.common.other_objects import AuthMethod

class FakePasswordHasher:   # pylint: disable=R0903
    """Fake password hasher for testing purposes."""
    def hash(self, password: str) -> str:
        """Returns a fake hash for the given password."""
        return f"fake-hash-{password}"

def test_initial_admin_is_created_once_with_configured_hash(
    tmp_path: Path,
) -> None:
    """Verifies than inital admin once and keeps its configured password hash."""
    database_settings = DatabaseSettings(DB_PATH=str(tmp_path / "initial-admin.db"))
    flask_settings = FlaskSettings(
        AUTH_MODE='internal',
        FLASK_ENV='testing',
        SECRET_KEY='test-secret-key-with-more-than-thirty-two-characters',
        ADMIN_USERNAME='initial-admin',
        ADMIN_PASSWORD="configured-password",
        ENFORCE_SECURE_CONNECTION=False,
        SESSION_COOKIE_SECURE=False,
    )
    hasher_settings = PasswordHasherSettings(
        TIME_COST=1,
        MEMORY_COST=8192,
        PARALLELISM=1,
        HASH_LEN=32,
        SALT_LEN=16,
    )
    first_app = create_app(flask_settings, database_settings, hasher_settings)
    try:
        manager = first_app.extensions["auth_manager"]
        admin = manager.user_service.get_by_username(flask_settings.ADMIN_USERNAME)

        assert admin is not None
        assert admin.is_admin

        internal_credentials = [
            credential
            for credential in admin.credentials
            if credential.auth_method == AuthMethod.INTERNAL.value
        ]
        assert len(internal_credentials) == 1

        original_id = str(admin.id)
        original_hash = internal_credentials[0].hash_password
        parameters = extract_parameters(original_hash)

        assert parameters.time_cost == hasher_settings.TIME_COST
        assert parameters.memory_cost == hasher_settings.MEMORY_COST
        assert parameters.parallelism == hasher_settings.PARALLELISM
        assert PasswordHasher().verify(
            original_hash,
            flask_settings.ADMIN_PASSWORD,
        )
    finally:
        first_app.extensions["database_config"].close()

    second_app = create_app(flask_settings, database_settings, hasher_settings)
    try:
        manager = second_app.extensions["auth_manager"]
        admin = manager.user_service.get_by_username(flask_settings.ADMIN_USERNAME)

        assert admin is not None
        assert str(admin.id) == original_id

        internal_credentials = [
            credential
            for credential in admin.credentials
            if credential.auth_method == AuthMethod.INTERNAL.value
        ]
        assert len(internal_credentials) == 1
        assert internal_credentials[0].hash_password == original_hash
    finally:
        second_app.extensions["database_config"].close()


def test_settings_load_password_hasher_values_from_nested_yaml(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Charge les paramètres imbriqués sous auth.password_hasher."""
    config_file = tmp_path / "config.yml"
    config_file.write_text(
        "auth:\n"
        "  password_hasher:\n"
        "    time_cost: 5\n"
        "    memory_cost: 131072\n"
        "    parallelism: 4\n"
        "    hash_len: 48\n"
        "    salt_len: 24\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("TTL_LAMA_CONFIG_FILE", str(config_file))
    for variable in (
        "TTL_LAMA_TIME_COST",
        "TTL_LAMA_MEMORY_COST",
        "TTL_LAMA_PARALLELISM",
        "TTL_LAMA_HASH_LEN",
        "TTL_LAMA_SALT_LEN",
    ):
        monkeypatch.delenv(variable, raising=False)

    settings = PasswordHasherSettings()

    assert settings.TIME_COST == 5
    assert settings.MEMORY_COST == 131072
    assert settings.PARALLELISM == 4
    assert settings.HASH_LEN == 48
    assert settings.SALT_LEN == 24


def test_settings_do_not_impose_parameter_limits() -> None:
    """Laisse le choix des paramètres matériels à l’opérateur."""
    settings = PasswordHasherSettings(
        TIME_COST=1,
        MEMORY_COST=1,
        PARALLELISM=1,
        HASH_LEN=4,
        SALT_LEN=8,
    )

    assert settings.TIME_COST == 1
    assert settings.MEMORY_COST == 1


def test_create_app_passes_password_hasher_settings_to_internal_backend(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Transmet les paramètres configurés au hasher du backend interne."""
    def create_fake_hasher(**kwargs: int) -> FakePasswordHasher:
        constructor_arguments.update(kwargs)
        return hasher_instance

    constructor_arguments: dict[str, int] = {}
    hasher_instance = FakePasswordHasher()

    monkeypatch.setattr("api.bootstrap.PasswordHasher", create_fake_hasher)
    flask_settings = FlaskSettings(
        AUTH_MODE="internal",
        FLASK_ENV="testing",
        SECRET_KEY="test-secret-key-with-more-than-thirty-two-characters",
        ENFORCE_SECURE_CONNECTION=False,
        SESSION_COOKIE_SECURE=False,
    )
    password_hasher_settings = PasswordHasherSettings(
        TIME_COST=5,
        MEMORY_COST=131072,
        PARALLELISM=4,
        HASH_LEN=48,
        SALT_LEN=24,
    )
    app = create_app(
        flask_settings,
        DatabaseSettings(DB_PATH=str(tmp_path / "test.db")),
        password_hasher_settings,
    )

    try:
        manager = app.extensions["auth_manager"]
        assert constructor_arguments == {
            "time_cost": 5,
            "memory_cost": 131072,
            "parallelism": 4,
            "hash_len": 48,
            "salt_len": 24,
        }
        assert manager.backend.password_hasher is hasher_instance
    finally:
        app.extensions["database_config"].close()
