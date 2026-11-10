"""Run administrator-defined actions after an unrecoverable reconciliation error.

.. classes::
    - ``PanicMailSettings``: Optional email notification configuration.
    - ``PanicSettings``: Panic-mode configuration loaded from the main YAML file.
    - ``SMTPSettings``: SMTP server configuration.
    - ``PanicMode``: Execute the configured script and optional email notification.

.. module_author:: Rémi Verschuur <rverschuur@audit-io.fr>
.. version:: 1.0.0
"""
from __future__ import annotations

import logging
import os
import smtplib
import subprocess
from email.message import EmailMessage
from pathlib import Path
from typing import Literal, cast

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

from api.logging_config import log_event

LOGGER = logging.getLogger(__name__)
DEFAULT_CONFIG_FILE = Path("/etc/ttl-lama/config.yml")
SCRIPT_TIMEOUT_SECONDS = 30
SMTP_TIMEOUT_SECONDS = 10


class PanicMailSettings(BaseModel):
    """Optional notification settings.

    :param send: Whether email notification is enabled.
    :type send: bool
    :param to: Notification recipient.
    :type to: str
    :param subject: Notification subject.
    :type subject: str
    :param body: Configured notification body.
    :type body: str
    :param config_file: Path to the SMTP YAML file.
    :type config_file: pathlib.Path | None
    :param secret_file: Path to the SMTP password file.
    :type secret_file: pathlib.Path | None
    """

    model_config = ConfigDict(extra="forbid")

    send: bool = False
    to: str = ""
    subject: str = "TTL-LAMa panic notification"
    body: str = "A backend reconciliation failed."
    config_file: Path | None = None
    secret_file: Path | None = None

    @model_validator(mode="after")
    def validate_enabled_mail(self) -> PanicMailSettings:
        """Require the recipient and SMTP file when email is enabled."""
        if self.send and (not self.to or self.config_file is None):
            raise ValueError("Enabled panic email requires a recipient and config_file")
        return self


class PanicSettings(BaseModel):
    """Panic-mode settings parsed from the main configuration file.

    :param mode: Panic activation mode.
    :type mode: typing.Literal['on_error', 'disabled']
    :param retry: Consecutive reconciliation failures before activation.
    :type retry: int
    :param script: Optional administrator script path.
    :type script: pathlib.Path | None
    :param notify: Master switch for email notification.
    :type notify: bool
    :param mail: Email notification configuration.
    :type mail: PanicMailSettings
    """

    model_config = ConfigDict(extra="forbid")

    mode: Literal["on_error", "disabled"] = "on_error"
    retry: int = Field(default=3, ge=1, le=10)
    script: Path | None = None
    notify: bool = False
    mail: PanicMailSettings = Field(default_factory=PanicMailSettings)

    @classmethod
    def from_file(cls, path: Path | None = None) -> PanicSettings:
        """Load panic settings from the application YAML file.

        :param path: Optional application configuration path.
        :type path: pathlib.Path | None
        :returns: Validated panic settings.
        :rtype: PanicSettings
        :raises ValueError: If the configuration file is unreadable or invalid.
        """
        config_path = path or Path(os.environ.get(
            "TTL_LAMA_CONFIG_FILE", str(DEFAULT_CONFIG_FILE),
        ))
        try:
            document: object = yaml.safe_load(config_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, yaml.YAMLError) as error:
            raise ValueError("Unable to read panic configuration") from error

        if document is None:
            return cls()
        if not isinstance(document, dict):
            raise ValueError("Application configuration must contain a mapping")
        panic_values = cast(dict[str, object], document).get("panic", {})
        if not isinstance(panic_values, dict):
            raise ValueError("Panic configuration must contain a mapping")
        try:
            return cls.model_validate(panic_values)
        except ValueError as error:
            raise ValueError("Panic configuration is invalid") from error


class SMTPSettings(BaseModel):
    """Validated SMTP connection settings.

    :param host: SMTP server hostname.
    :type host: str
    :param port: SMTP server port.
    :type port: int
    :param username: Optional SMTP account name.
    :type username: str | None
    :param use_tls: Whether to negotiate STARTTLS.
    :type use_tls: bool
    """

    model_config = ConfigDict(extra="forbid")

    host: str = Field(min_length=1, max_length=255)
    port: int = Field(default=587, ge=1, le=65535)
    username: str | None = None
    use_tls: bool = True


class PanicMode:    # pylint: disable=R0903
    """Execute administrator-defined responses to reconciliation failure.

    :param settings: Validated panic-mode settings.
    :type settings: PanicSettings
    """

    def __init__(self, settings: PanicSettings) -> None:
        self.settings = settings

    def trigger(self, reason: str) -> None:
        """Run the configured script and independently attempt notification.

        :param reason: Safe summary of the reconciliation failure.
        :type reason: str
        """
        if self.settings.mode == "disabled":
            return

        if self.settings.script is not None:
            try:
                subprocess.run(
                    [str(self.settings.script)],
                    check=True,
                    capture_output=True,
                    text=True,
                    timeout=SCRIPT_TIMEOUT_SECONDS,
                )
            except (OSError, subprocess.SubprocessError) as error:
                log_event(
                    LOGGER,
                    logging.WARNING,
                    "panic.script",
                    "failed error=%s",
                    type(error).__name__,
                )
            else:
                log_event(LOGGER, logging.INFO, "panic.script", "succeeded")

        if self.settings.notify and self.settings.mail.send:
            try:
                self._send_email(reason)
            except (OSError, yaml.YAMLError, ValueError) as error:
                log_event(
                    LOGGER,
                    logging.WARNING,
                    "panic.email",
                    "failed error=%s",
                    type(error).__name__,
                )
            else:
                log_event(LOGGER, logging.INFO, "panic.email", "succeeded")

    def _send_email(self, reason: str) -> None:
        mail = self.settings.mail
        if mail.config_file is None:
            raise ValueError("SMTP configuration file is missing")
        try:
            document: object = yaml.safe_load(mail.config_file.read_text(encoding="utf-8"))
            smtp_settings = SMTPSettings.model_validate(document)
        except (OSError, yaml.YAMLError, ValueError) as error:
            raise ValueError("SMTP configuration is invalid") from error

        password: str | None = None
        if smtp_settings.username is not None:
            if mail.secret_file is None:
                raise ValueError("SMTP password file is missing")
            try:
                password = mail.secret_file.read_text(encoding="utf-8").strip()
            except (OSError, UnicodeError) as error:
                raise ValueError("Unable to read SMTP password") from error

        message = EmailMessage()
        message["From"] = smtp_settings.username or "ttlama@localhost"
        message["To"] = mail.to
        message["Subject"] = mail.subject
        message.set_content(f"{mail.body.rstrip()}\n\n{reason}\n")

        with smtplib.SMTP(
            smtp_settings.host,
            smtp_settings.port,
            timeout=SMTP_TIMEOUT_SECONDS,
        ) as client:
            if smtp_settings.use_tls:
                client.starttls()
            if smtp_settings.username is not None and password is not None:
                client.login(smtp_settings.username, password)
            client.send_message(message)
