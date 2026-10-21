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
from enum import Enum
from typing import Any
from sqlalchemy import create_engine, Engine, URL, text
from sqlalchemy.schema import CreateSchema
from sqlalchemy.orm import scoped_session, sessionmaker

from pydantic import computed_field, Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

LOGGER = logging.getLogger(__name__)


class DbType(str, Enum):
    """Enumeration of supported database types.
    
    .. SQLITE:: SQLite database type.
        - type: str
        - value: "sqlite"

    .. POSTGRESQL:: PostgreSQL database type.
        - type: str
        - value: "postgres"

    .. MYSQL:: MySQL database type.
        - type: str
        - value: "mysql"
    .. MARIADB:: MariaDB database type.
        - type: str
        - value: "mariadb"
    """
    SQLITE = "sqlite"
    POSTGRESQL = "postgres"
    MYSQL = "mysql"
    MARIADB = "mariadb"


class Settings(BaseSettings):
    """Database settings for the TTL-LAMa API.
    
    :param model_config: Configuration for the Pydantic model.
    :type model_config: SettingsConfigDict
    :param EXTERNAL_DB: Indicates if an external database is used.
    :type EXTERNAL_DB: bool
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
    :param DB_NAME: Database name.
    :type DB_NAME: str
    :param DB_SCHEMA: Database schema.
    :type DB_SCHEMA: str
    :param db_url: Constructed database URL based on the configuration.
    :type db_url: str | URL

    .. methods::
        - `db_url()`: Returns the constructed database URL based on the configuration.
        - `validate_database_config()`: Validates the database configuration after model
        initialization.

    .. author:: Rémi Verschuur <rverschuur@audit-io.fr>
    .. version:: 1.0.0
    """
    model_config = SettingsConfigDict(
        env_file = "/etc/app/env.conf",
        extra = "ignore",
    )

    EXTERNAL_DB: bool = False
    DB_PATH: str = "/var/lib/app/database.db"
    DB_TYPE: DbType = DbType.SQLITE

    DB_HOST: str = "localhost"
    DB_PORT: int = Field(default=0, ge=0, le=65535)

    DB_USER: str = ""
    DB_PASSWORD: str = ""

    DB_NAME: str = "appdb"
    DB_SCHEMA: str = "public"

    @computed_field
    @property
    def db_url(self) -> str | URL:
        """Construct the database URL from the individual components.

        :return: Constructed database URL based on the configuration.
        :rtype: str | URL

        :raises ValueError: If the database configuration is invalid.
        """
        if not self.EXTERNAL_DB and self.DB_TYPE != DbType.SQLITE:
            LOGGER.error(
                "Invalid database configuration: If not external, DB_TYPE have to be SQLITE"
            )
            raise ValueError(f"If not external, DB_TYPE have to be {DbType.SQLITE}")
        if not self.EXTERNAL_DB or self.DB_TYPE == DbType.SQLITE:
            LOGGER.info("Using SQLite database at path: %s", self.DB_PATH)
            return f"sqlite:///{self.DB_PATH}"
        url_param: dict[str, Any] = {
            "username": self.DB_USER,
            "password": self.DB_PASSWORD,
            "host": self.DB_HOST,
            "port": self.DB_PORT,
            "database": self.DB_NAME,
        }
        hpd_string = (
            "Host: %s, Port: %s, Database: %s",
            self.DB_HOST,
            self.DB_PORT,
            self.DB_NAME,
        )
        if self.DB_TYPE == DbType.POSTGRESQL:
            url_base = URL.create(
                drivername="postgresql+psycopg2",
                **url_param,
            )
            LOGGER.info(
                "Using PostgreSQL database with postresql+psycopg2. %s",
                hpd_string,
            )
            return url_base
        if self.DB_TYPE == DbType.MYSQL:
            url_base = URL.create(
                drivername="mysql+pymysql",
                **url_param,
            )
            LOGGER.info(
                "Using MySQL database with mysql+pymysql. %s",
                hpd_string,
            )
            return url_base
        if self.DB_TYPE == DbType.MARIADB:
            LOGGER.info(
                "Using MariaDB database with mariadb+pymysql. %s",
                hpd_string,
            )
            return URL.create(drivername="mariadb+pymysql", **url_param)
        LOGGER.error(
            "Unsupported DB_TYPE for external database: %s. " +
            "Supported types are: %s",
            self.DB_TYPE,
            [
                DbType.SQLITE.value,
                DbType.POSTGRESQL.value,
                DbType.MYSQL.value,
                DbType.MARIADB.value,
            ])
        raise ValueError(f"Unsupported DB_TYPE for external database: {self.DB_TYPE}")

    @model_validator(mode="after")
    def validate_database_config(self):
        """Validate the database configuration after model initialization.

        :raises ValueError: If the database configuration is invalid.
        """
        if not self.EXTERNAL_DB and self.DB_TYPE != DbType.SQLITE:
            LOGGER.error(
                "If not external, DB_TYPE have to be %s. ",
                DbType.SQLITE,
            )
            raise ValueError(f"If not external, DB_TYPE have to be {DbType.SQLITE}")
        return self


class DatabaseConfig:   # pylint: disable=R0903
    """Class representing the database configuration.
    
    :param settings: The application settings containing the database configuration.
    :type settings: Settings

    .. methods::
        - `__init__`: Initializes the database configuration with the provided settings.
        - `initialize`: Initializes the spatial prerequisites and missing tables.
        - `_create_engine`: Creates the SQLAlchemy engine based on the configuration.
        - `_configure_sqlite`: Configures the SQLite engine.
        - `_configure_postgresql`: Configures the PostgreSQL engine.
        - `_configure_mysql`: Configures the MySQL/MariaDB engine.

    .. author:: Rémi Verschuur <rverschuur@audit-io.fr>
    .. version:: 1.0.0
    """
    def __init__(self, settings: Settings):
        """Initialize the database configuration with the provided settings.

        :param settings: The application settings containing the database configuration.
        :type settings: Settings

        :raises SQLAlchemyError: If the database engine cannot be created.
        """
        self.settings = settings
        self.engine = self._create_engine()
        self.session = scoped_session(
            sessionmaker(
                bind=self.engine,
                autoflush=False,
                expire_on_commit=False,
            ),
        )

    def initialize(self) -> None:
        """Initialize the spatial prerequisites and the missing tables.
        
        :return: None
        :rtype: None

        :raises SQLAlchemyError: If there is an error during the initialization of the database.
        """
        from api.common.db_objects.users import (   # pylint: disable=C0415
            Group,
            User,
            UserGroup,
            UserSession,
            UserLoginState,
            UserIdentity,
            AuthRuntimeState,
        )

        with self.engine.begin() as connection:
            if self.settings.DB_TYPE == DbType.POSTGRESQL:
                connection.execute(text("CREATE EXTENSION IF NOT EXISTS postgis"))
                connection.execute(CreateSchema(self.settings.DB_SCHEMA, if_not_exists=True))
            User.metadata.create_all(connection, checkfirst=True)
            Group.metadata.create_all(connection, checkfirst=True)
            UserGroup.metadata.create_all(connection, checkfirst=True)
            UserSession.metadata.create_all(connection, checkfirst=True)
            UserLoginState.metadata.create_all(connection, checkfirst=True)
            UserIdentity.metadata.create_all(connection, checkfirst=True)
            AuthRuntimeState.metadata.create_all(connection, checkfirst=True)

    def _create_engine(self) -> Engine:
        """
        Create the SQLAlchemy engine separating the configuration between SQLite
        and external databases.

        :return: The configured SQLAlchemy engine.
        :rtype: Engine

        :raises SQLAlchemyError: If the database engine cannot be created or configured.
        """
        engine = create_engine(self.settings.db_url)

        if self.settings.DB_TYPE == DbType.SQLITE:
            self._configure_sqlite(engine)
        elif self.settings.DB_TYPE == DbType.POSTGRESQL:
            self._configure_postgresql(engine)
        elif self.settings.DB_TYPE in {DbType.MYSQL, DbType.MARIADB}:
            self._configure_mysql(engine)

        return engine

    def _configure_sqlite(self, engine: Engine) -> None:
        """Configure SQLite-specific settings for the SQLAlchemy engine.
        
        :param engine: The SQLAlchemy engine to configure for SQLite.
        :type engine: Engine
        :return: None
        :rtype: None

        :raises sqlite3.Error: If spatial metadata cannot be initialized.
        """

    def _configure_postgresql(self, engine: Engine) -> None:
        """Configure PostgreSQL-specific settings for the SQLAlchemy engine.

        :param engine: The SQLAlchemy engine to configure for PostgreSQL.
        :type engine: Engine
        :return: None
        :rtype: None
        """

    def _configure_mysql(self, engine: Engine) -> None:
        """Configure MySQL-specific settings for the SQLAlchemy engine.

        :param engine: The SQLAlchemy engine to configure for MySQL.
        :type engine: Engine
        :return: None
        :rtype: None
        """
