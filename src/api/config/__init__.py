"""Configuration package for the TTL-LAMa API.

.. classes::
    - `AccessProfile`: Validated access-policy model.
    - `AccessProfiles`: Collection of configured access profiles.
    - `FlaskSettings`: Flask application settings.
    - `DatabaseSettings`: Database connection settings.
    - `DatabaseConfig`: Database initialization and connection management.
    
.. module_author:: Rémi Verschuur <rverschuur@audit-io.fr>
.. version:: 1.0.0
"""
from __future__ import annotations

from .c_flask import Settings as FlaskSettings
from .c_databases import Settings as DatabaseSettings, DatabaseConfig
from .c_profiles import AccessProfile, AccessProfiles

__all__ = [
    "AccessProfile",
    "AccessProfiles",
    "FlaskSettings",
    "DatabaseSettings",
    "DatabaseConfig",
]
