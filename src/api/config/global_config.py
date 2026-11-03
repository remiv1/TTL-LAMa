"""Helpers for reading and safely persisting the application configuration.

.. functions::
    - ``configuration_path``: Return the configured YAML file path.
    - ``load_configuration``: Load the application configuration document.
    - ``redact_secrets``: Mask direct secret values in a configuration document.
    - ``validate_configuration``: Validate a candidate against application settings.
    - ``write_configuration``: Atomically persist a validated YAML document.
    - ``is_volume_mounted``: Check whether a path is covered by a container mount.

.. module_author:: Rémi Verschuur <rverschuur@audit-io.fr>
.. version:: 1.0.0
"""
from __future__ import annotations

import copy
import os
import re
import stat
import tempfile
from pathlib import Path
from typing import cast

import yaml
from pydantic import BaseModel, ValidationError

from . import DatabaseSettings, FlaskSettings, PasswordHasherSettings

REDACTED = "[REDACTED]"
SECRET_PATHS = (
    ("app", "secret_key"),
    ("auth", "admin", "password"),
    ("auth", "oidc", "client_secret"),
    ("database", "password"),
)
SETTINGS_MODELS: tuple[type[BaseModel], ...] = (
    FlaskSettings,
    DatabaseSettings,
    PasswordHasherSettings,
)


class GlobalConfigError(Exception):
    """Represent an error while accessing the configured YAML document."""


def configuration_path() -> Path:
    """Return the server-side application YAML path."""
    return Path(os.environ.get("TTL_LAMA_CONFIG_FILE", "/etc/ttl-lama/config.yml"))


def load_configuration() -> dict[str, object]:
    """Read the configured YAML document as a mapping.

    :returns: The configuration mapping.
    :rtype: dict[str, object]
    :raises GlobalConfigError: If the file cannot be read or is not a mapping.
    """
    try:
        value: object = yaml.safe_load(configuration_path().read_text(encoding="utf-8"))
    except (OSError, UnicodeError, yaml.YAMLError) as error:
        raise GlobalConfigError("Unable to read the application configuration.") from error
    if not isinstance(value, dict):
        raise GlobalConfigError("The application configuration must be a YAML object.")
    return cast(dict[str, object], value)


def redact_secrets(configuration: dict[str, object]) -> dict[str, object]:
    """Mask direct secrets without modifying the loaded configuration.

    :param configuration: The loaded YAML document.
    :type configuration: dict[str, object]
    :returns: A deep copy with direct secret values masked.
    :rtype: dict[str, object]
    """
    result = copy.deepcopy(configuration)
    for path in SECRET_PATHS:
        section = result
        for key in path[:-1]:
            value = section.get(key)
            if not isinstance(value, dict):
                break
            section = cast(dict[str, object], value)
        else:
            if path[-1] in section:
                section[path[-1]] = REDACTED
    return result


def _contains_redacted(value: object) -> bool:
    if value == REDACTED:
        return True
    if isinstance(value, dict):
        return any(
            _contains_redacted(item)
            for item in cast(dict[object, object], value).values()
        )
    if isinstance(value, list):
        return any(_contains_redacted(item) for item in cast(list[object], value))
    return False


def validate_configuration(configuration: object) -> list[str]:
    """Validate a candidate using the existing application settings models.

    :param configuration: The candidate document received from the CLI.
    :type configuration: object
    :returns: Validation errors, or an empty list when the document is valid.
    :rtype: list[str]
    """
    if not isinstance(configuration, dict):
        return ["The configuration must be a YAML object."]
    if _contains_redacted(cast(dict[str, object], configuration)):
        return ["Replace [REDACTED] with a value or a secret-file reference."]

    errors: list[str] = []
    for settings_model in SETTINGS_MODELS:
        try:
            settings_model.model_validate(configuration)
        except ValidationError as error:
            for item in error.errors(
                include_input=False,
                include_context=False,
                include_url=False,
            ):
                location = ".".join(str(part) for part in item["loc"])
                message = str(item["msg"])
                errors.append(f"{location}: {message}" if location else message)
        except (TypeError, ValueError) as error:
            errors.append(str(error))
    return errors


def write_configuration(configuration: dict[str, object]) -> None:
    """Atomically replace the configured YAML file.

    :param configuration: A validated application configuration document.
    :type configuration: dict[str, object]
    :raises GlobalConfigError: If the target cannot be written.
    """
    path = configuration_path()
    temporary_path: Path | None = None
    try:
        current_mode = stat.S_IMODE(path.stat().st_mode) if path.exists() else 0o600
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{path.name}.",
            suffix=".tmp",
            dir=path.parent,
        )
        temporary_path = Path(temporary_name)
        with os.fdopen(descriptor, "w", encoding="utf-8") as temporary_file:
            os.fchmod(temporary_file.fileno(), current_mode)
            yaml.safe_dump(configuration, temporary_file, sort_keys=False, allow_unicode=True)
            temporary_file.flush()
            os.fsync(temporary_file.fileno())
        os.replace(temporary_path, path)
        directory_descriptor = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory_descriptor)
        finally:
            os.close(directory_descriptor)
    except (OSError, UnicodeError, yaml.YAMLError) as error:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)
        raise GlobalConfigError("Unable to write the application configuration.") from error


def is_volume_mounted(
    path: Path,
    mountinfo_path: Path = Path("/proc/self/mountinfo"),
) -> bool:
    """Check whether a non-root container mount covers a target path.

    :param path: The configuration file path.
    :type path: Path
    :param mountinfo_path: Linux mount information file, overridable for tests.
    :type mountinfo_path: Path
    :returns: Whether a non-root mount contains the target path.
    :rtype: bool
    """
    try:
        mountinfo = mountinfo_path.read_text(encoding="utf-8")
    except OSError:
        return False

    target = path.resolve(strict=False)
    for line in mountinfo.splitlines():
        fields = line.split()
        if len(fields) < 5:
            continue
        mountpoint = Path(
            re.sub(
                r"\\([0-7]{3})",
                lambda match: chr(int(match.group(1), 8)), fields[4]
            )
        )
        mountpoint = mountpoint.resolve(strict=False)
        if mountpoint == Path("/"):
            continue
        try:
            target.relative_to(mountpoint)
            return True
        except ValueError:
            continue
    return False
