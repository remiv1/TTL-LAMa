"""Initialization for the database objects package.

.. classes::
    - `Base`: base class for all database objects.

.. constantes::
    - `TABLE_ARGS`: default table arguments for the database objects.

.. functions::
    - `foreign_key_target(table_name: str, column_name: str = "id") -> str`: Constructs a
    foreign key reference compatible with the active schema.
    - `table_key(table_name: str) -> str`: Returns the metadata key of a table according to
    the active schema.

.. module_author:: Rémi Verschuur <rverschuur@audit-io.fr>
.. version:: 1.0
"""
from __future__ import annotations

from typing import Any
import logging

from sqlalchemy.orm import DeclarativeBase

from ...config import DatabaseSettings
from ...config.c_databases import DbType

settings = DatabaseSettings()

TABLE_ARGS = {"schema": settings.DB_SCHEMA} if settings.DB_TYPE == DbType.POSTGRESQL else {}
LOGGER = logging.getLogger(__name__)


def foreign_key_target(table_name: str, column_name: str = "id") -> str:
    """Constructs a foreign key reference compatible with the active schema.

    :param table_name: Name of the table for the foreign key reference.
    :type table_name: str
    :param column_name: Name of the column for the foreign key reference (default is "id").
    :type column_name: str
    :returns: The foreign key reference as a string.
    :rtype: str
    """
    return f"{table_key(table_name)}.{column_name}"


def table_key(table_name: str) -> str:
    """Returns the metadata key of a table according to the active schema.

    :param table_name: Name of the table.
    :type table_name: str
    :returns: The metadata key of the table.
    :rtype: str
    """
    schema = TABLE_ARGS.get("schema")
    return f"{schema}.{table_name}" if schema else table_name

class Base(DeclarativeBase):
    """Base class for all database objects.
    
    .. author:: Rémi Verschuur <rverschuur@audit-io.fr>
    .. version:: 1.0
    """

    def to_dict(self) -> dict[str, Any]:
        """Converts the database object to a dictionary.
        
        :returns: The database object as a dictionary.
        :rtype: dict[str, Any]
        """
        return {c.name: getattr(self, c.name) for c in self.__table__.columns}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Any:
        """Creates a database object from a dictionary.

        :param data: The dictionary containing the database object data.
        :type data: dict[str, Any]
        :returns: The created database object.
        :rtype: Any

        .. note::
            This method assumes that the keys in the dictionary match the attribute names
            of the database object. Extra keys in the dictionary will be ignored.
        
        .. example::
            ```python
            data = response.to_json()
            obj = MyDatabaseObject.from_dict(data)
            ```
        """
        obj = cls()
        for key, value in data.items():
            if hasattr(obj, key):
                setattr(obj, key, value)
            else:
                LOGGER.debug("Unknown attribute '%s' in data dictionary", key)
        return obj
