"""Database configuration for the TTL-LAMa API.

.. classes::
    - `DbType`: Enumeration of supported database types.
    - `Settings`: Contains the database configuration settings for the TTL-LAMa API.
    - `DatabaseConfig`: Represents the database configuration and provides methods for
    initialization and engine creation.

.. module_author:: Rémi Verschuur <rverschuur@audit-io.fr>
.. version:: 1.0.0
"""
from __future__ import annotations

import logging
import os
import sqlite3
from enum import Enum
from pathlib import Path

from pydantic import Field, computed_field, model_validator
from pydantic_settings import (
    BaseSettings,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
    YamlConfigSettingsSource,
)
from sqlalchemy import Engine, URL, create_engine, event
from sqlalchemy.orm import Session, scoped_session, sessionmaker
from sqlalchemy.schema import CreateSchema

LOGGER = logging.getLogger(__name__)


class DbType(str, Enum):
    """Enumeration of supported database types.

    Supported values are ``sqlite``, ``postgresql``, ``mysql``, and ``mariadb``.
    """

    SQLITE = "sqlite"
    POSTGRESQL = "postgresql"
    MYSQL = "mysql"
    MARIADB = "mariadb"


class Settings(BaseSettings):
    """Database settings for the TTL-LAMa API.

    :param model_config: Configuration for the Pydantic model.
    :type model_config: SettingsConfigDict
    :param DB_PATH: Path to the SQLite database file.
    :type DB_PATH: str
    :param DB_TYPE: Type of the database (SQLite, PostgreSQL, MySQL, MariaDB).
    :type DB_TYPE: DbType
    :param DB_HOST: Database host.
    :type DB_HOST: str
    :param DB_PORT: Database port.
    :type DB_PORT: int
    :param DB_USER: Database user.
    :type DB_USER: str
    :param DB_PASSWORD: Database password.
    :type DB_PASSWORD: str
    :param DB_PASSWORD_FILE: Path to the mounted database password.
    :type DB_PASSWORD_FILE: Path | None
    :param DB_NAME: Database name.
    :type DB_NAME: str
    :param DB_SCHEMA: Database schema.
    :type DB_SCHEMA: str
    :param db_url: Constructed database URL based on the configuration.
    :type db_url: str | URL

    .. methods::
        - `settings_customise_sources`: Set the settings-source priority.
        - `normalize_database_yaml`: Map nested database YAML to model fields.
        - `validate_database_config`: Resolve secrets and validate database settings.
        - `db_url`: Build the SQLAlchemy URL.

    .. author:: Rémi Verschuur <rverschuur@audit-io.fr>
    .. version:: 1.0.0
    """

    model_config = SettingsConfigDict(
        yaml_file="/etc/ttl-lama/config.yml",
        env_prefix="TTL_LAMA_",
        env_nested_delimiter="__",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    DB_TYPE: DbType = DbType.SQLITE
    DB_PATH: str = "/data/ttl-lama.db"
    DB_HOST: str = "localhost"
    DB_PORT: int = Field(default=0, ge=0, le=65535)
    DB_USER: str = ""
    DB_PASSWORD: str = Field(default="", repr=False)
    DB_PASSWORD_FILE: Path | None = Field(default=None, repr=False)
    DB_NAME: str = "ttl_lama"
    DB_SCHEMA: str = "public"

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        """Place environment variables before the YAML configuration.

        :param settings_cls: The settings class being configured.
        :type settings_cls: type[BaseSettings]
        :param init_settings: Values passed directly to the settings constructor.
        :type init_settings: PydanticBaseSettingsSource
        :param env_settings: Values loaded from environment variables.
        :type env_settings: PydanticBaseSettingsSource
        :param dotenv_settings: Values loaded from an optional dotenv file.
        :type dotenv_settings: PydanticBaseSettingsSource
        :param file_secret_settings: Values loaded from Pydantic secret files.
        :type file_secret_settings: PydanticBaseSettingsSource
        :returns: Settings sources ordered from highest to lowest priority.
        :rtype: tuple[PydanticBaseSettingsSource, ...]

        .. note::
            Constructor arguments and environment variables override YAML values.
        """
        config_file = os.environ.get(
            "TTL_LAMA_CONFIG_FILE",
            "/etc/ttl-lama/config.yml",
        )
        yaml_settings = YamlConfigSettingsSource(
            settings_cls,
            yaml_file=config_file,
        )
        return (
            init_settings,
            env_settings,
            yaml_settings,
            dotenv_settings,
            file_secret_settings,
        )

    @model_validator(mode="before")
    @classmethod
    def normalize_database_yaml(cls, values: object) -> object:
        """Flatten the structured database section into settings fields.

        :param values: The raw settings document.
        :type values: object
        :returns: The normalized settings mapping.
        :rtype: object
        """
        if not isinstance(values, dict):
            return values
        database = values.get("database")
        if not isinstance(database, dict):
            return values
        normalized = dict(values)
        key_mapping = {
            "type": "DB_TYPE",
            "path": "DB_PATH",
            "host": "DB_HOST",
            "port": "DB_PORT",
            "user": "DB_USER",
            "password": "DB_PASSWORD",
            "password_file": "DB_PASSWORD_FILE",
            "name": "DB_NAME",
            "schema": "DB_SCHEMA",
        }
        for key, field_name in key_mapping.items():
            if key in database:
                normalized.setdefault(field_name, database[key])
        if normalized.get("DB_TYPE") == "postgres":
            normalized["DB_TYPE"] = DbType.POSTGRESQL
        return normalized

    @model_validator(mode="after")
    def validate_database_config(self) -> Settings:
        """Resolve the database password and validate external database settings.

        :returns: The validated database settings.
        :rtype: Settings
        :raises ValueError: If the secret source or external database settings are invalid.
        """
        if self.DB_PASSWORD_FILE is not None:
            if self.DB_PASSWORD:
                raise ValueError("Configurer DB_PASSWORD ou DB_PASSWORD_FILE, pas les deux")
            try:
                self.DB_PASSWORD = self.DB_PASSWORD_FILE.read_text(
                    encoding="utf-8",
                ).rstrip("\r\n")
            except OSError as error:
                raise ValueError("Impossible de lire le fichier secret DB_PASSWORD") from error
        if self.DB_TYPE != DbType.SQLITE:
            if not self.DB_HOST or not self.DB_NAME or not self.DB_USER:
                raise ValueError(
                    "DB_HOST, DB_NAME et DB_USER sont requis pour une base externe"
                )
            if not self.DB_PASSWORD:
                raise ValueError(
                    "DB_PASSWORD ou DB_PASSWORD_FILE est requis pour une base externe"
                )
        return self

    @computed_field
    @property
    def db_url(self) -> str | URL:
        """Build the SQLAlchemy URL for the configured database.

        :returns: A SQLite URL or a structured URL for an external database.
        :rtype: str | sqlalchemy.engine.URL
        """
        if self.DB_TYPE == DbType.SQLITE:
            if self.DB_PATH == ":memory:":
                return "sqlite://"
            return f"sqlite:///{Path(self.DB_PATH).expanduser()}"

        default_ports = {
            DbType.POSTGRESQL: 5432,
            DbType.MYSQL: 3306,
            DbType.MARIADB: 3306,
        }
        driver_names = {
            DbType.POSTGRESQL: "postgresql+psycopg2",
            DbType.MYSQL: "mysql+pymysql",
            DbType.MARIADB: "mariadb+pymysql",
        }
        return URL.create(
            drivername=driver_names[self.DB_TYPE],
            username=self.DB_USER,
            password=self.DB_PASSWORD,
            host=self.DB_HOST,
            port=self.DB_PORT or default_ports[self.DB_TYPE],
            database=self.DB_NAME,
        )


class DatabaseConfig:
    """Class representing the database configuration.

    :param settings: The application settings containing the database configuration.
    :type settings: Settings

    .. methods::
        - `__init__`: Initializes the database configuration with the provided settings.
        - `initialize`: Initializes the missing tables.
        - `close`: Closes the database session and engine.
        - `_create_engine`: Creates the SQLAlchemy engine based on the configuration.
        - `_prepare_sqlite_directory`: Creates the parent directory for a file database.
        - `_configure_sqlite_connection`: Applies SQLite connection settings.

    .. author:: Rémi Verschuur <rverschuur@audit-io.fr>
    .. version:: 1.0.0
    """

    def __init__(self, settings: Settings) -> None:
        """Create the database engine and scoped session factory.

        :param settings: Validated database settings.
        :type settings: Settings
        """
        self.settings = settings
        self.engine = self._create_engine()
        self.session: scoped_session[Session] = scoped_session(
            sessionmaker(
                bind=self.engine,
                autoflush=False,
                expire_on_commit=False,
            ),
        )

    def initialize(self) -> None:
        """Initialize the missing tables.

        :raises SQLAlchemyError: If schema or table initialization fails.
        """
        from api.common.db_objects import Base
        from api.common.db_objects.users import User

        with self.engine.begin() as connection:
            if self.settings.DB_TYPE == DbType.POSTGRESQL:
                connection.execute(
                    CreateSchema(self.settings.DB_SCHEMA, if_not_exists=True),
                )
            Base.metadata.create_all(connection, checkfirst=True)
        LOGGER.debug("Initialized database tables for %s", User.__tablename__)

    def close(self) -> None:
        """Remove the scoped session and dispose of the database engine.

        :returns: ``None``.
        :rtype: None
        """
        self.session.remove()
        self.engine.dispose()

    def _create_engine(self) -> Engine:
        """Create the configured engine and apply dialect-specific options.

        :returns: The configured SQLAlchemy engine.
        :rtype: sqlalchemy.engine.Engine
        """
        from api.common.db_objects import TABLE_SCHEMA_TOKEN

        if self.settings.DB_TYPE == DbType.SQLITE:
            self._prepare_sqlite_directory()
            engine = create_engine(
                self.settings.db_url,
                connect_args={"check_same_thread": False, "timeout": 30},
            )
            event.listen(engine, "connect", self._configure_sqlite_connection)
            return engine.execution_options(
                schema_translate_map={TABLE_SCHEMA_TOKEN: None},
            )

        engine = create_engine(self.settings.db_url, pool_pre_ping=True)
        schema = (
            self.settings.DB_SCHEMA
            if self.settings.DB_TYPE == DbType.POSTGRESQL
            else None
        )
        return engine.execution_options(
            schema_translate_map={TABLE_SCHEMA_TOKEN: schema},
        )

    def _prepare_sqlite_directory(self) -> None:
        """Create the parent directory for a file-backed SQLite database.

        :returns: ``None``.
        :rtype: None
        """
        if self.settings.DB_PATH == ":memory:":
            return
        Path(self.settings.DB_PATH).expanduser().parent.mkdir(
            parents=True,
            exist_ok=True,
        )

    @staticmethod
    def _configure_sqlite_connection(
        connection: sqlite3.Connection,
        _record: object,
    ) -> None:
        """Enable foreign keys and a bounded lock wait on SQLite connections.

        :param connection: The newly opened SQLite DB-API connection.
        :type connection: sqlite3.Connection
        :param _record: The SQLAlchemy connection record.
        :type _record: object
        :returns: ``None``.
        :rtype: None
        """
        cursor = connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA busy_timeout=30000")
        cursor.close()
