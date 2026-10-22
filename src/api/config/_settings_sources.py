"""Shared base class for settings loaded from environment and YAML sources.

.. module_author:: Rémi Verschuur <rverschuur@audit-io.fr>
.. version:: 1.0.0
"""
from __future__ import annotations

import os

from pydantic_settings import (
    BaseSettings,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
    YamlConfigSettingsSource,
)


class YamlSettingsBase(BaseSettings):
    """Base settings with the application's shared source priority.

    .. note::
        Sources are ordered as constructor, environment, YAML, dotenv, and secret files.
    
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

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        """Place environment variables before YAML configuration.

        :returns: Settings sources in priority order.
        :rtype: tuple[PydanticBaseSettingsSource, ...]
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
