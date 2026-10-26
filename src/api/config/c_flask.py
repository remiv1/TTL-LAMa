"""Configuration module for TTL-LAMa.

This module contains the configuration settings for the TTL-LAMa application.

.. classes::
    - `Settings`: Contains the configuration settings for the TTL-LAMa application.

.. module_author:: Rémi Verschuur <rverschuur@audit-io.fr>
.. version:: 1.0.0
"""
from __future__ import annotations

import logging
import re
from pathlib import Path

from typing import Literal, cast
from urllib.parse import urlparse

from pydantic import Field, model_validator
from ._settings_sources import YamlSettingsBase

LOGGER = logging.getLogger(__name__)
COOKIE_NAME_PATTERN = re.compile(r"^[!#$%&'*+\-.^_`|~0-9A-Za-z]+$")
_MAX_CONTENT_LENGTH = 2 * 1024 * 1024  # 2 MB

class Settings(YamlSettingsBase):
    """Flask application, authentication, and HTTP security settings.

    .. attributes::
        - ``FLASK_ENV``: Application environment.
        - ``DEBUG``: Enable or disable debug mode.
        - ``SECRET_KEY``: Flask secret key.
        - ``SECRET_KEY_FILE``: Path to the file containing the Flask secret key.
        - ``AUTH_MODE``: Internal or external authentication mode.
        - ``ADMIN_USERNAME``: Administrator username.
        - ``ADMIN_PASSWORD``: Administrator password.
        - ``ADMIN_PASSWORD_FILE``: Path to the file containing the administrator password.
        - ``OIDC_ISSUER``: External identity provider issuer.
        - ``OIDC_CLIENT_ID``: External identity provider client ID.
        - ``OIDC_CLIENT_SECRET``: External identity provider client secret.
        - ``OIDC_CLIENT_SECRET_FILE``: Path to the file containing the external identity provider client secret.
        - ``OIDC_REDIRECT_URI``: External identity provider redirect URI.
        - ``ACCESS_PROFILES_FILE``: Path to the access profiles file.
        - ``AUTH_COOKIE_NAME``: Authentication cookie name.
        - ``SERVER_HOST``: Server host address.
        - ``SERVER_PORT``: Server port number.
        - ``SESSION_LIFETIME``: Session lifetime in seconds.
        - ``SESSION_COOKIE_NAME``: Flask session cookie name.
        - ``ENFORCE_SECURE_CONNECTION``: Whether HTTPS is required.
        - ``SESSION_COOKIE_HTTPONLY``: Whether the session cookie is HTTP-only.
        - ``SESSION_COOKIE_SECURE``: Whether the session cookie is secure.
        - ``SESSION_COOKIE_SAMESITE``: SameSite attribute for the session cookie.
        - ``SESSION_COOKIE_PATH``: Path attribute for the session cookie.
        - ``SESSION_LIFETIME``: Session lifetime in seconds.
        - ``MAX_CONTENT_LENGTH``: Maximum content length for requests.
        - ``TESTING``: Enable or disable testing mode.
    """

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
    SESSION_LIFETIME: int = 3600
    MAX_CONTENT_LENGTH: int = _MAX_CONTENT_LENGTH
    TESTING: bool = Field(default=False)

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

        normalized: dict[str, object] = cast(dict[str, object], values)
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
                "session_lifetime": "SESSION_LIFETIME",
            },
            "access_profiles": {
                "file": "ACCESS_PROFILES_FILE",
            },
        }
        for section_name, key_mapping in mappings.items():
            cls._copy_section_values(
                normalized,
                normalized.get(section_name),
                key_mapping,
            )

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
        auth = normalized.get("auth")
        if isinstance(auth, dict):
            auth_values = cast(dict[str, object], auth)
            for section_name, key_mapping in nested_auth.items():
                cls._copy_section_values(
                    normalized,
                    auth_values.get(section_name),
                    key_mapping,
                )
        return normalized

    @staticmethod
    def _copy_section_values(
        normalized: dict[str, object],
        section: object,
        key_mapping: dict[str, str],
    ) -> None:
        if not isinstance(section, dict):
            return
        section_values = cast(dict[str, object], section)
        for key, field_name in key_mapping.items():
            if key in section_values:
                normalized.setdefault(field_name, section_values[key])

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
        self._resolve_authentication_secrets()
        is_production = self.model_dump()["FLASK_ENV"].lower() == "production"
        self._validate_environment(is_production)
        if self.AUTH_MODE == "external":
            self._validate_oidc_configuration(is_production)
        return self

    def _resolve_authentication_secrets(self) -> None:
        setattr(
            self,
            "SECRET_KEY",
            self._read_secret("SECRET_KEY", self.SECRET_KEY, self.SECRET_KEY_FILE),
        )
        if self.AUTH_MODE == "internal":
            setattr(
                self,
                "ADMIN_PASSWORD",
                self._read_secret(
                    "ADMIN_PASSWORD",
                    self.ADMIN_PASSWORD,
                    self.ADMIN_PASSWORD_FILE,
                ),
            )
        else:
            setattr(
                self,
                "OIDC_CLIENT_SECRET",
                self._read_secret(
                    "OIDC_CLIENT_SECRET",
                    self.OIDC_CLIENT_SECRET,
                    self.OIDC_CLIENT_SECRET_FILE,
                ),
            )
        if len(self.SECRET_KEY) < 32:
            raise ValueError("SECRET_KEY doit contenir au moins 32 caractères")

    def _validate_environment(self, is_production: bool) -> None:
        if is_production and self.DEBUG:
            raise ValueError("DEBUG doit être désactivé en production")
        if is_production and not self.ENFORCE_SECURE_CONNECTION:
            raise ValueError(
                "ENFORCE_SECURE_CONNECTION doit être activé en production"
            )

    def _validate_oidc_configuration(self, is_production: bool) -> None:
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
            or (is_production and issuer.scheme != "https")
        ):
            raise ValueError("OIDC_ISSUER doit être une URL HTTPS en production")
        redirect = urlparse(self.OIDC_REDIRECT_URI)
        if (
            redirect.scheme not in {"http", "https"}
            or not redirect.netloc
            or redirect.path != "/auth/callback"
            or (is_production and redirect.scheme != "https")
        ):
            raise ValueError("OIDC_REDIRECT_URI doit pointer vers /auth/callback")

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
