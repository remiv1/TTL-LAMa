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

from typing import Literal
from urllib.parse import urlparse

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

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
    :param LOG_LEVEL: The logging level for the application.
    :type LOG_LEVEL: str
    :param AUTH_MODE: The authentication mode ("none", "internal", or "external").
    :type AUTH_MODE: Literal["none", "internal", "external"]
    :param ADMIN_USERNAME: The username for the initial administrator (internal mode).
    :type ADMIN_USERNAME: str
    :param ADMIN_PASSWORD: The password for the initial administrator (internal mode).
    :type ADMIN_PASSWORD: str
    :param OIDC_ISSUER: The OIDC issuer URL (external mode).
    :type OIDC_ISSUER: str
    :param OIDC_CLIENT_ID: The OIDC client ID (external mode).
    :type OIDC_CLIENT_ID: str
    :param OIDC_CLIENT_SECRET: The OIDC client secret (external mode).
    :type OIDC_CLIENT_SECRET: str
    :param OIDC_REDIRECT_URI: The OIDC redirect URI (external mode).
    :type OIDC_REDIRECT_URI: str
    :param AUTH_COOKIE_NAME: The name of the authentication cookie.
    :type AUTH_COOKIE_NAME: str
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
        - `validate_authentication`: Validates the authentication-related settings based
        on the chosen authentication mode.
        - `_validate_cookie_names`: Validates the names of the authentication and session cookies.
        - `_validate_flask_cookie_settings`: Validates the Flask session cookie settings.

    .. author:: Rémi Verschuur <rverschuur@audit-io.fr>
    .. version:: 1.0.0
    """
    model_config = SettingsConfigDict(
        env_file="/etc/app/env.conf",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    FLASK_ENV: str = Field(default="production")
    DEBUG: bool = Field(default=False, validation_alias="flask_debug")
    SECRET_KEY: str = Field(default="default_secret_key")
    LOG_LEVEL: str = Field(default="info")
    AUTH_MODE: Literal["none", "internal", "external"] = "none"
    ALLOW_ANONYMOUS_ACCESS: bool = False
    ADMIN_USERNAME: str = "admin"
    ADMIN_PASSWORD: str = Field(default="", repr=False)
    OIDC_ISSUER: str = ""
    OIDC_CLIENT_ID: str = ""
    OIDC_CLIENT_SECRET: str = Field(default="", repr=False)
    OIDC_REDIRECT_URI: str = ""
    AUTH_COOKIE_NAME: str = "ttl-lama_session"
    SESSION_COOKIE_NAME: str = "session"
    ENFORCE_SECURE_CONNECTION: bool = False
    SESSION_COOKIE_HTTPONLY: bool = True
    SESSION_COOKIE_SECURE: bool = False
    SESSION_COOKIE_SAMESITE: str = "Lax"
    SESSION_COOKIE_PATH: str = "/"
    MAX_CONTENT_LENGTH: int = _MAX_CONTENT_LENGTH

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
        if self.AUTH_MODE == "none":
            if (
                self.FLASK_ENV.lower() == "production"  # pylint: disable=E1101
                and "AUTH_MODE" in self.model_fields_set
                and not self.ALLOW_ANONYMOUS_ACCESS
            ):
                LOGGER.exception(
                    "ALLOW_ANONYMOUS_ACCESS must be enabled when AUTH_MODE is 'none' in production"
                )
                raise ValueError(
                    "ALLOW_ANONYMOUS_ACCESS doit etre active pour utiliser "
                    "AUTH_MODE=none en production"
                )
            LOGGER.debug("Authentication mode is set to 'none'")
            return self
        if self.SECRET_KEY == "default_secret_key" or len(self.SECRET_KEY) < 32:
            LOGGER.error("SECRET_KEY is default or shorter than 32 characters")
            raise ValueError(
                "SECRET_KEY doit être personnalisé et contenir au moins 32 caractères "
                "hors du mode none"
            )
        if self.AUTH_MODE == "external":
            required = (
                self.OIDC_ISSUER,
                self.OIDC_CLIENT_ID,
                self.OIDC_CLIENT_SECRET,
                self.OIDC_REDIRECT_URI,
            )
            if not all(required):
                absent = [
                    name for name in [
                        "OIDC_ISSUER",
                        "OIDC_CLIENT_ID",
                        "OIDC_CLIENT_SECRET",
                        "OIDC_REDIRECT_URI",
                    ] if name not in required
                ]
                if absent:
                    LOGGER.exception(
                        "OIDC configuration is incomplete: missing %s",
                        ", ".join(absent)
                    )
                raise ValueError("La configuration OIDC est incomplete")
            if urlparse(self.OIDC_REDIRECT_URI).path != "/auth/callback":
                LOGGER.exception(
                    "OIDC_REDIRECT_URI must point to /auth/callback, but got %s",
                    self.OIDC_REDIRECT_URI
                )
                raise ValueError("OIDC_REDIRECT_URI doit pointer vers /auth/callback")
        return self
