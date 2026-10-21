"""Configuration package for the TTL-LAMa API.

.. classes::
    - `FlaskSettings`: Configuration settings for Flask.
    - `DatabaseSettings`: Configuration settings for the database.
    - `DatabaseConfig`: Database configuration and connection management.
    
.. module_author:: Rémi Verschuur <rverschuur@audit-io.fr>
.. version:: 1.0.0
"""
from __future__ import annotations

from .c_flask import Settings as FlaskSettings
from .c_databases import Settings as DatabaseSettings, DatabaseConfig

__all__ = [
    "FlaskSettings",
    "DatabaseSettings",
    "DatabaseConfig",
]
