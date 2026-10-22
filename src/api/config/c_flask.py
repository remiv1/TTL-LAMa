"""Configuration module for TTL-LAMa.

This module contains the configuration settings for the TTL-LAMa application.

.. classes::
    - `Settings`: Contains the configuration settings for the TTL-LAMa application.

.. module_author:: Rémi Verschuur <rverschuur@audit-io.fr>
.. version:: 1.0.0
"""
from __future__ import annotations

import logging
import os
import re
from pathlib import Path

from typing import Literal
from urllib.parse import urlparse

from pydantic import Field, model_validator
from pydantic_settings import (
    BaseSettings,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
    YamlConfigSettingsSource,
)

LOGGER = logging.getLogger(__name__)
COOKIE_NAME_PATTERN = re.compile(r"^[!#$%&'*+\-.^_`|~0-9A-Za-z]+$")
_MAX_CONTENT_LENGTH = 2 * 1024 * 1024  # 2 MB

class Settings(BaseSettings):
    """Settings for the TTL-LAMa application.
    
    :param model_config: The configuration for the Pydantic model.
    :type model_config: SettingsConfigDict
    :param FLASK_ENV: The Flask environment (e.g., "production" or "development").
    :type FLASK_ENV: str
    :param DEBUG: Whether to enable Flask debug mode.
    :type DEBUG: bool
    :param SECRET_KEY: The secret key for the Flask application.
    :type SECRET_KEY: str
    :param SECRET_KEY_FILE: Path to the mounted Flask secret key.
    :type SECRET_KEY_FILE: Path | None
    :param LOG_LEVEL: The logging level for the application.
    :type LOG_LEVEL: str
    :param AUTH_MODE: The authentication mode, either internal or external.
    :type AUTH_MODE: Literal["internal", "external"]
    :param ADMIN_USERNAME: The username for the initial administrator (internal mode).
    :type ADMIN_USERNAME: str
    :param ADMIN_PASSWORD: The password for the initial administrator (internal mode).
    :type ADMIN_PASSWORD: str
    :param ADMIN_PASSWORD_FILE: Path to the mounted administrator password.
    :type ADMIN_PASSWORD_FILE: Path | None
    :param OIDC_ISSUER: The OIDC issuer URL (external mode).
    :type OIDC_ISSUER: str
    :param OIDC_CLIENT_ID: The OIDC client ID (external mode).
    :type OIDC_CLIENT_ID: str
    :param OIDC_CLIENT_SECRET: The OIDC client secret (external mode).
    :type OIDC_CLIENT_SECRET: str
    :param OIDC_CLIENT_SECRET_FILE: Path to the mounted OIDC client secret.
    :type OIDC_CLIENT_SECRET_FILE: Path | None
    :param OIDC_REDIRECT_URI: The OIDC redirect URI (external mode).
    :type OIDC_REDIRECT_URI: str
    :param ACCESS_PROFILES_FILE: Path to the declarative access-profile file.
    :type ACCESS_PROFILES_FILE: Path | None
    :param AUTH_COOKIE_NAME: The name of the authentication cookie.
    :type AUTH_COOKIE_NAME: str
    :param SERVER_HOST: The address on which the WSGI server listens.
    :type SERVER_HOST: str
    :param SERVER_PORT: The port on which the WSGI server listens.
    :type SERVER_PORT: int
    :param ENFORCE_SECURE_CONNECTION: Whether requests must use HTTPS.
    :type ENFORCE_SECURE_CONNECTION: bool
    :param SESSION_COOKIE_NAME: The name of the Flask session cookie.
    :type SESSION_COOKIE_NAME: str
    :param SESSION_COOKIE_HTTPONLY: Whether the Flask session cookie is HttpOnly.
    :type SESSION_COOKIE_HTTPONLY: bool
    :param SESSION_COOKIE_SECURE: Whether the Flask session cookie requires HTTPS.
    :type SESSION_COOKIE_SECURE: bool
    :param SESSION_COOKIE_SAMESITE: SameSite policy for the Flask session cookie.
    :type SESSION_COOKIE_SAMESITE: str
    :param SESSION_COOKIE_PATH: Path scope for the Flask session cookie.
    :type SESSION_COOKIE_PATH: str
    :param MAX_CONTENT_LENGTH: The maximum allowed size for incoming request bodies.
    :type MAX_CONTENT_LENGTH: int

    .. methods::
        - `normalize_nested_yaml`: Maps structured YAML sections to settings fields.
        - `settings_customise_sources`: Configures settings-source priority.
        - `validate_authentication`: Validates the authentication-related settings based
        on the chosen authentication mode.
        - `_validate_cookie_names`: Validates the names of the authentication and session cookies.
        - `_validate_flask_cookie_settings`: Validates the Flask session cookie settings.
        - `_read_secret`: Resolves a secret from a mounted file or direct value.

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

    FLASK_ENV: str = Field(default="production")
    DEBUG: bool = Field(default=False)
    SECRET_KEY: str = Field(default="", repr=False)
    SECRET_KEY_FILE: Path | None = Field(default=None, repr=False)
    LOG_LEVEL: str = Field(default="info")
    AUTH_MODE: Literal["internal", "external"] = "internal"
    ADMIN_USERNAME: str = "admin"
    ADMIN_PASSWORD: str = Field(default="", repr=False)
    ADMIN_PASSWORD_FILE: Path | None = Field(default=None, repr=False)
    OIDC_ISSUER: str = ""
    OIDC_CLIENT_ID: str = ""
    OIDC_CLIENT_SECRET: str = Field(default="", repr=False)
    OIDC_CLIENT_SECRET_FILE: Path | None = Field(default=None, repr=False)
    OIDC_REDIRECT_URI: str = ""
    ACCESS_PROFILES_FILE: Path | None = None
    AUTH_COOKIE_NAME: str = "ttl-lama_session"
    SERVER_HOST: str = "0.0.0.0"
    SERVER_PORT: int = Field(default=8080, ge=1, le=65535)
    SESSION_COOKIE_NAME: str = "session"
    ENFORCE_SECURE_CONNECTION: bool = True
    SESSION_COOKIE_HTTPONLY: bool = True
    SESSION_COOKIE_SECURE: bool = True
    SESSION_COOKIE_SAMESITE: str = "Lax"
    SESSION_COOKIE_PATH: str = "/"
    MAX_CONTENT_LENGTH: int = _MAX_CONTENT_LENGTH

    @model_validator(mode="before")
    @classmethod
    def normalize_nested_yaml(cls, values: object) -> object:
        """Flatten the structured YAML sections into the settings field names.

        :param values: The raw settings document.
        :type values: object
        :returns: The normalized settings mapping.
        :rtype: object
        """
        if not isinstance(values, dict):
            return values

        normalized = dict(values)
        mappings = {
            "app": {
                "environment": "FLASK_ENV",
                "debug": "DEBUG",
                "secret_key": "SECRET_KEY",
                "secret_key_file": "SECRET_KEY_FILE",
                "log_level": "LOG_LEVEL",
                "max_content_length": "MAX_CONTENT_LENGTH",
            },
            "server": {
                "host": "SERVER_HOST",
                "port": "SERVER_PORT",
            },
            "auth": {
                "mode": "AUTH_MODE",
                "cookie_name": "AUTH_COOKIE_NAME",
            },
            "security": {
                "enforce_secure_connection": "ENFORCE_SECURE_CONNECTION",
                "session_cookie_name": "SESSION_COOKIE_NAME",
                "session_cookie_httponly": "SESSION_COOKIE_HTTPONLY",
                "session_cookie_secure": "SESSION_COOKIE_SECURE",
                "session_cookie_samesite": "SESSION_COOKIE_SAMESITE",
                "session_cookie_path": "SESSION_COOKIE_PATH",
            },
            "access_profiles": {
                "file": "ACCESS_PROFILES_FILE",
            },
        }
        for section_name, key_mapping in mappings.items():
            section = normalized.get(section_name)
            if isinstance(section, dict):
                for key, field_name in key_mapping.items():
                    if key in section:
                        normalized.setdefault(field_name, section[key])

        auth = normalized.get("auth")
        if isinstance(auth, dict):
            nested_auth = {
                "admin": {
                    "username": "ADMIN_USERNAME",
                    "password": "ADMIN_PASSWORD",
                    "password_file": "ADMIN_PASSWORD_FILE",
                },
                "oidc": {
                    "issuer": "OIDC_ISSUER",
                    "client_id": "OIDC_CLIENT_ID",
                    "client_secret": "OIDC_CLIENT_SECRET",
                    "client_secret_file": "OIDC_CLIENT_SECRET_FILE",
                    "redirect_uri": "OIDC_REDIRECT_URI",
                },
            }
            for section_name, key_mapping in nested_auth.items():
                section = auth.get(section_name)
                if isinstance(section, dict):
                    for key, field_name in key_mapping.items():
                        if key in section:
                            normalized.setdefault(field_name, section[key])
        return normalized

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

    def _validate_cookie_names(self) -> None:
        """Validate the names of the authentication and session cookies.

        :raises ValueError: If the cookie names are invalid or if they are the same.
        """
        for setting_name, cookie_name in (
            ("AUTH_COOKIE_NAME", self.AUTH_COOKIE_NAME),
            ("SESSION_COOKIE_NAME", self.SESSION_COOKIE_NAME),
        ):
            if not COOKIE_NAME_PATTERN.fullmatch(cookie_name):
                raise ValueError(f"{setting_name} doit être un nom de cookie valide")
        if self.AUTH_COOKIE_NAME == self.SESSION_COOKIE_NAME:
            raise ValueError(
                "Les noms des cookies d'authentification et Flask doivent différer"
            )

    def _validate_flask_cookie_settings(self) -> None:
        """Validate the Flask session cookie settings.

        :raises ValueError: If any of the Flask session cookie settings are invalid.
        """
        if not self.SESSION_COOKIE_HTTPONLY:
            raise ValueError("SESSION_COOKIE_HTTPONLY doit rester activé")
        if self.SESSION_COOKIE_SAMESITE != "Lax":
            raise ValueError("SESSION_COOKIE_SAMESITE doit être Lax")
        if self.SESSION_COOKIE_PATH != "/":
            raise ValueError("SESSION_COOKIE_PATH doit être /")
        if self.SESSION_COOKIE_SECURE != self.ENFORCE_SECURE_CONNECTION:
            if "SESSION_COOKIE_SECURE" in self.model_fields_set:
                raise ValueError(
                    "SESSION_COOKIE_SECURE doit correspondre à "
                    "ENFORCE_SECURE_CONNECTION"
                )
            self.SESSION_COOKIE_SECURE = self.ENFORCE_SECURE_CONNECTION # type: ignore # pylint: disable=C0103

    @model_validator(mode="after")
    def validate_authentication(self) -> Settings:
        """Validate the necessary secrets for the chosen authentication mode.
        
        :return: The validated settings instance.
        :rtype: Self

        :raises ValueError: If the authentication-related settings are invalid.
        """
        self._validate_cookie_names()
        self._validate_flask_cookie_settings()
        self.SECRET_KEY = self._read_secret(
            "SECRET_KEY",
            self.SECRET_KEY,
            self.SECRET_KEY_FILE,
        )
        if self.AUTH_MODE == "internal":
            self.ADMIN_PASSWORD = self._read_secret(
                "ADMIN_PASSWORD",
                self.ADMIN_PASSWORD,
                self.ADMIN_PASSWORD_FILE,
            )
        else:
            self.OIDC_CLIENT_SECRET = self._read_secret(
                "OIDC_CLIENT_SECRET",
                self.OIDC_CLIENT_SECRET,
                self.OIDC_CLIENT_SECRET_FILE,
            )
        if len(self.SECRET_KEY) < 32:
            raise ValueError("SECRET_KEY doit contenir au moins 32 caractères")
        if self.FLASK_ENV.lower() == "production" and self.DEBUG:
            raise ValueError("DEBUG doit être désactivé en production")
        if self.FLASK_ENV.lower() == "production" and not self.ENFORCE_SECURE_CONNECTION:
            raise ValueError(
                "ENFORCE_SECURE_CONNECTION doit être activé en production"
            )
        if self.AUTH_MODE == "external":
            required = (
                self.OIDC_ISSUER,
                self.OIDC_CLIENT_ID,
                self.OIDC_CLIENT_SECRET,
                self.OIDC_REDIRECT_URI,
            )
            if not all(required):
                raise ValueError("La configuration OIDC est incomplete")
            issuer = urlparse(self.OIDC_ISSUER)
            if (
                not issuer.netloc
                or issuer.scheme not in {"http", "https"}
                or (
                    self.FLASK_ENV.lower() == "production"
                    and issuer.scheme != "https"
                )
            ):
                raise ValueError("OIDC_ISSUER doit être une URL HTTPS en production")
            redirect = urlparse(self.OIDC_REDIRECT_URI)
            if (
                redirect.scheme not in {"http", "https"}
                or not redirect.netloc
                or redirect.path != "/auth/callback"
                or (
                    self.FLASK_ENV.lower() == "production"
                    and redirect.scheme != "https"
                )
            ):
                raise ValueError("OIDC_REDIRECT_URI doit pointer vers /auth/callback")
        return self

    @staticmethod
    def _read_secret(name: str, value: str, secret_file: Path | None) -> str:
        """Read a secret from its configured file or use its direct value.

        :param name: The setting name used in validation errors.
        :type name: str
        :param value: The secret value supplied directly.
        :type value: str
        :param secret_file: The mounted file containing the secret, if configured.
        :type secret_file: Path | None
        :returns: The resolved secret value.
        :rtype: str
        :raises ValueError: If both sources are configured or the file cannot be read.
        """
        if secret_file is None:
            return value
        if value:
            raise ValueError(f"Configurer {name} ou son fichier, pas les deux")
        try:
            return secret_file.read_text(encoding="utf-8").rstrip("\r\n")
        except OSError as error:
            raise ValueError(f"Impossible de lire le fichier secret {name}") from error
