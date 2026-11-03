"""Tests de la configuration du hasher de mots de passe."""

from pathlib import Path

import pytest
from argon2 import PasswordHasher, extract_parameters

from api.bootstrap import create_app
from api.config import DatabaseConfig, DatabaseSettings, FlaskSettings
from api.config.c_password_hasher import Settings as PasswordHasherSettings
from api.common.db_objects import User, UserCredentials, UserOIDCUser
from api.local_admin import main as local_admin_main
from api.common.other_objects import AuthMethod
from auth.services.user import UserService


def _write_external_admin_config(tmp_path: Path, database_path: Path) -> Path:
    config_file = tmp_path / "external-admin.yml"
    config_file.write_text(
        "app:\n"
        "  environment: testing\n"
        "  secret_key: test-secret-key-with-more-than-thirty-two-characters\n"
        "auth:\n"
        "  mode: external\n"
        "  admin:\n"
        "    username: initial-admin\n"
        "  oidc:\n"
        "    issuer: http://dex.example.test/dex/\n"
        "    client_id: ttl-lama-dex\n"
        "    client_secret: ttl-lama-test-secret\n"
        "    redirect_uri: http://127.0.0.1:8080/auth/callback\n"
        "database:\n"
        "  type: sqlite\n"
        f'  path: "{database_path}"\n'
        "security:\n"
        "  enforce_secure_connection: false\n"
        "  session_cookie_secure: false\n",
        encoding="utf-8",
    )
    return config_file

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


def test_local_command_creates_external_admin_once_without_internal_credentials(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Prepare the external admin at startup before linking its OIDC identity."""
    config_file = _write_external_admin_config(
        tmp_path,
        tmp_path / "external-admin.db",
    )
    monkeypatch.setenv("TTL_LAMA_CONFIG_FILE", str(config_file))

    app = create_app(FlaskSettings(), DatabaseSettings())
    try:
        admin = app.extensions["auth_manager"].user_service.get_by_username(
            "initial-admin"
        )
        assert admin is not None
        assert admin.enabled
        assert admin.is_admin
        assert admin.credentials == []
        assert admin.oidc_users == []
    finally:
        app.extensions["database_config"].close()

    arguments = ["bootstrap-oidc-admin", "--user-id", "admin-subject"]
    assert local_admin_main(arguments) == 0
    assert local_admin_main(arguments) == 0

    database = DatabaseConfig(DatabaseSettings())
    try:
        database.initialize()
        user_service = UserService(database.session())
        admin = user_service.get_by_username("initial-admin")
        assert admin is not None
        assert admin.enabled
        assert admin.is_admin
        assert admin.credentials == []
        assert len(admin.oidc_users) == 1
        linked_admin = user_service.get_by_oidc(
            "http://dex.example.test/dex", "admin-subject"
        )
        assert linked_admin is not None
        assert linked_admin.id == admin.id
    finally:
        database.close()

def test_external_bootstrap_links_existing_admin_without_changing_credentials(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Link an existing account without changing its state or credential."""
    database_settings = DatabaseSettings(DB_PATH=str(tmp_path / "existing-admin.db"))
    internal_settings = FlaskSettings(
        AUTH_MODE="internal",
        FLASK_ENV="testing",
        SECRET_KEY="test-secret-key-with-more-than-thirty-two-characters",
        ADMIN_USERNAME="internal-bootstrap-admin",
        ADMIN_PASSWORD="initial-password",
        ENFORCE_SECURE_CONNECTION=False,
        SESSION_COOKIE_SECURE=False,
    )
    internal_app = create_app(internal_settings, database_settings)
    try:
        user_service = internal_app.extensions["auth_manager"].user_service
        existing_user = User(
            username="initial-admin",
            enabled=False,
            is_admin=False,
        )
        user_service.add_user(existing_user).add_credential(
            UserCredentials(
                auth_method=AuthMethod.INTERNAL.value,
                hash_password=PasswordHasher().hash("existing-password"),
            )
        ).create()
        original_id = str(existing_user.id)
        original_hash = existing_user.credentials[0].hash_password
    finally:
        internal_app.extensions["database_config"].close()

    config_file = _write_external_admin_config(
        tmp_path,
        Path(database_settings.DB_PATH),
    )
    monkeypatch.setenv("TTL_LAMA_CONFIG_FILE", str(config_file))
    assert local_admin_main([
        "bootstrap-oidc-admin",
        "--user-id",
        "admin-subject",
    ]) == 0

    database = DatabaseConfig(DatabaseSettings())
    try:
        database.initialize()
        user_service = UserService(database.session())
        admin = user_service.get_by_username("initial-admin")
        assert admin is not None
        assert str(admin.id) == original_id
        assert not admin.enabled
        assert not admin.is_admin
        assert admin.credentials[0].hash_password == original_hash
        linked_admin = user_service.get_by_oidc(
            "http://dex.example.test/dex", "admin-subject"
        )
        assert linked_admin is not None
        assert linked_admin.id == admin.id
    finally:
        database.close()


def test_external_startup_does_not_prepare_admin_when_oidc_identity_exists(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Skip initial admin preparation when the OIDC table is already populated."""
    database_path = tmp_path / "existing-oidc-identity.db"
    internal_app = create_app(
        FlaskSettings(
            AUTH_MODE="internal",
            FLASK_ENV="testing",
            SECRET_KEY="test-secret-key-with-more-than-thirty-two-characters",
            ENFORCE_SECURE_CONNECTION=False,
            SESSION_COOKIE_SECURE=False,
        ),
        DatabaseSettings(DB_PATH=str(database_path)),
    )
    try:
        owner = User(
            username="pre-provisioned-user",
            enabled=True,
            is_admin=False,
            oidc_users=[UserOIDCUser(
                issuer="http://dex.example.test/dex",
                subject="existing-subject",
            )],
        )
        internal_app.extensions["auth_manager"].user_service.add_user(owner).create()
    finally:
        internal_app.extensions["database_config"].close()

    config_file = _write_external_admin_config(tmp_path, database_path)
    monkeypatch.setenv("TTL_LAMA_CONFIG_FILE", str(config_file))
    external_app = create_app(FlaskSettings(), DatabaseSettings())
    try:
        user_service = external_app.extensions["auth_manager"].user_service
        assert user_service.get_by_username("initial-admin") is None
        assert user_service.get_by_oidc(
            "http://dex.example.test/dex",
            "existing-subject",
        ) is not None
    finally:
        external_app.extensions["database_config"].close()


def test_first_oidc_identity_link_is_allowed_only_once(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Allow one OIDC identity link and reject a different later identity."""
    config_file = _write_external_admin_config(
        tmp_path,
        tmp_path / "first-oidc-link.db",
    )
    monkeypatch.setenv("TTL_LAMA_CONFIG_FILE", str(config_file))
    app = create_app(FlaskSettings(), DatabaseSettings())
    try:
        user_service = app.extensions["auth_manager"].user_service
        admin = user_service.get_by_username("initial-admin")
        assert admin is not None
        assert admin.oidc_users == []

        linked_admin = user_service.link_first_oidc_admin_identity(
            "initial-admin",
            "http://dex.example.test/dex",
            "first-subject",
        )
        assert linked_admin is not None
        assert linked_admin.id == admin.id

        second_link = user_service.link_first_oidc_admin_identity(
            "initial-admin",
            "http://dex.example.test/dex",
            "second-subject",
        )
        assert second_link is None
        assert user_service.get_by_oidc(
            "http://dex.example.test/dex", "first-subject"
        ) is not None
        assert user_service.get_by_oidc(
            "http://dex.example.test/dex", "second-subject"
        ) is None
    finally:
        app.extensions["database_config"].close()


def test_initial_oidc_admin_subject_cannot_belong_to_another_user(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Reject a Dex user ID that is already linked to another account."""
    database_path = tmp_path / "oidc-conflict.db"
    settings = FlaskSettings(
        AUTH_MODE="internal",
        FLASK_ENV="testing",
        SECRET_KEY="test-secret-key-with-more-than-thirty-two-characters",
        ENFORCE_SECURE_CONNECTION=False,
        SESSION_COOKIE_SECURE=False,
    )
    app = create_app(settings, DatabaseSettings(DB_PATH=str(database_path)))
    try:
        user_service = app.extensions["auth_manager"].user_service
        owner = User(
            username="other-user",
            is_admin=False,
            enabled=True,
            oidc_users=[UserOIDCUser(
                issuer="http://dex.example.test/dex",
                subject="admin-subject",
            )],
        )
        user_service.add_user(owner).create()
    finally:
        app.extensions["database_config"].close()

    config_file = _write_external_admin_config(tmp_path, database_path)
    monkeypatch.setenv("TTL_LAMA_CONFIG_FILE", str(config_file))
    assert local_admin_main([
        "bootstrap-oidc-admin",
        "--user-id",
        "admin-subject",
    ]) == 1

    external_database = DatabaseConfig(DatabaseSettings())
    try:
        external_database.initialize()
        user_service = UserService(external_database.session())
        assert user_service.get_by_username("initial-admin") is None
    finally:
        external_database.close()


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
