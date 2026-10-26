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
import sqlite3
from enum import Enum
from importlib import import_module
from pathlib import Path
from typing import cast

from pydantic import Field, computed_field, model_validator
from sqlalchemy import Engine, URL, create_engine, event
from sqlalchemy.orm import Session, scoped_session, sessionmaker
from sqlalchemy.schema import CreateSchema

from ._settings_sources import YamlSettingsBase

LOGGER = logging.getLogger(__name__)


class DbType(str, Enum):
    """Enumeration of supported database types.

    .. SQLITE:: SQLite database type.
        - type: str
        - value: "sqlite"

    .. POSTGRESQL:: PostgreSQL database type.
        - type: str
        - value: "postgresql"

    .. MYSQL:: MySQL database type.
        - type: str
        - value: "mysql"

    .. MARIADB:: MariaDB database type.
        - type: str
        - value: "mariadb"
    """

    SQLITE = "sqlite"
    POSTGRESQL = "postgresql"
    MYSQL = "mysql"
    MARIADB = "mariadb"


class Settings(YamlSettingsBase):
    """Database connection and persistence settings.

    .. attributes::
        - ``DB_TYPE``: Database engine type.
        - ``DB_PATH``: SQLite database file path.
        - ``DB_HOST``: External database host.
        - ``DB_NAME``: External database name.
        - ``DB_SCHEMA``: External database schema.
    """

    DB_TYPE: DbType = DbType.SQLITE
    DB_PATH: str = "/data/ttl-lama.db"
    DB_HOST: str = "localhost"
    DB_PORT: int = Field(default=0, ge=0, le=65535)
    DB_USER: str = ""
    DB_PASSWORD: str = Field(default="", repr=False)
    DB_PASSWORD_FILE: Path | None = Field(default=None, repr=False)
    DB_NAME: str = "ttl_lama"
    DB_SCHEMA: str = "public"

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

        source_values = cast(dict[str, object], values)
        database = source_values.get("database")
        if not isinstance(database, dict):
            return source_values
        normalized: dict[str, object] = dict(source_values)
        database_values = cast(dict[str, object], database)
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
            if key in database_values:
                normalized.setdefault(field_name, database_values[key])
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
        password_file = cast(Path | None, self.model_dump()["DB_PASSWORD_FILE"])
        password = self.DB_PASSWORD
        if password_file is not None:
            if password:
                raise ValueError("Configurer DB_PASSWORD ou DB_PASSWORD_FILE, pas les deux")
            try:
                password = password_file.read_text(
                    encoding="utf-8",
                ).rstrip("\r\n")
            except OSError as error:
                raise ValueError("Impossible de lire le fichier secret DB_PASSWORD") from error
            setattr(self, "DB_PASSWORD", password)
        if self.DB_TYPE != DbType.SQLITE:
            if not self.DB_HOST or not self.DB_NAME or not self.DB_USER:
                raise ValueError(
                    "DB_HOST, DB_NAME et DB_USER sont requis pour une base externe"
                )
            if not password:
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
        base_module = import_module("api.common.db_objects._common")
        user_module = import_module("api.common.db_objects.users")
        base_class = getattr(base_module, "Base")
        user_model = getattr(user_module, "User")

        with self.engine.begin() as connection:
            if self.settings.DB_TYPE == DbType.POSTGRESQL:
                connection.execute(
                    CreateSchema(self.settings.DB_SCHEMA, if_not_exists=True),
                )
            base_class.metadata.create_all(connection, checkfirst=True)
        LOGGER.debug("Initialized database tables for %s", user_model.__tablename__)

    def close(self) -> None:
        """Remove the scoped session and dispose of the database engine.

        :returns: ``None``.
        :rtype: None
        """
        self.session.remove()
        self.engine.dispose()

    def _create_engine(self) -> Engine:
        """Create the configured engine and apply SQLite connection settings.

        :returns: The configured SQLAlchemy engine.
        :rtype: sqlalchemy.engine.Engine
        """
        if self.settings.DB_TYPE == DbType.SQLITE:
            self._prepare_sqlite_directory()
            engine = create_engine(
                self.settings.db_url,
                connect_args={"check_same_thread": False, "timeout": 30},
            )
            event.listen(engine, "connect", self._configure_sqlite_connection)
            return engine

        return create_engine(self.settings.db_url, pool_pre_ping=True)

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
