"""Configuration for the password hasher.

This module defines the configuration parameters for the Argon2 password hasher,
including time cost, memory cost, parallelism, hash length, and salt length.


.. module_author:: Rémi Verschuur <rverschuur@audit-io.fr>
.. version:: 1.0.0
"""
from __future__ import annotations

from typing import cast

from pydantic import model_validator

from ._settings_sources import YamlSettingsBase


class Settings(YamlSettingsBase):
    """Paramètres du hasher Argon2id chargés depuis la configuration applicative."""

    TIME_COST: int = 3
    MEMORY_COST: int = 65536
    PARALLELISM: int = 4
    HASH_LEN: int = 32
    SALT_LEN: int = 16

    @model_validator(mode="before")
    @classmethod
    def normalize_password_hasher_yaml(cls, values: object) -> object:
        """Aplatir la section YAML auth.password_hasher vers les champs du modèle."""
        if not isinstance(values, dict):
            return values

        source_values = cast(dict[str, object], values)
        auth = source_values.get("auth")
        if not isinstance(auth, dict):
            return source_values

        password_hasher = cast(dict[str, object], auth).get("password_hasher")
        if not isinstance(password_hasher, dict):
            return source_values

        normalized = dict(source_values)
        key_mapping = {
            "time_cost": "TIME_COST",
            "memory_cost": "MEMORY_COST",
            "parallelism": "PARALLELISM",
            "hash_len": "HASH_LEN",
            "salt_len": "SALT_LEN",
        }
        hasher_values = cast(dict[str, object], password_hasher)
        for key, field_name in key_mapping.items():
            if key in hasher_values:
                normalized.setdefault(field_name, hasher_values[key])
        return normalized
