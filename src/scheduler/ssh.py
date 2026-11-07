"""Run commands on the VPN backend through a dedicated SSH connection.

.. classes::
    - `SSHConfiguration`: Validated SSH transport settings.
    - `SSHCommandExecutor`: Execute a command over SSH.

.. module_author:: Rémi Verschuur <rverschuur@audit-io.fr>
.. version:: 1.0.0
"""
from __future__ import annotations

import os
import math
import shlex
import subprocess
from collections.abc import Sequence
from pathlib import Path
from typing import cast

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError


class SSHConfiguration(BaseModel):
    """Validated connection settings loaded immediately before an SSH command.

    .. author:: Rémi Verschuur <rverschuur@audit-io.fr>
    .. version:: 1.0.0
    """

    model_config = ConfigDict(extra="forbid")

    host: str = Field(min_length=1, max_length=255)
    port: int = Field(gt=0, le=65535)
    user: str = Field(min_length=1, max_length=255)
    identity_file: Path
    known_hosts_file: Path
    connection_timeout: int = Field(gt=0)


class SSHCommandExecutor:
    """Execute a generic argument vector on the configured SSH host.

    :param config_path: Optional SSH configuration path, defaulting to
        ``/etc/ttl-lama/ssh_config.yml`` or ``TTL_LAMA_SSH_CONFIG_FILE``.
    :type config_path: Path | None

    .. author:: Rémi Verschuur <rverschuur@audit-io.fr>
    .. version:: 1.0.0
    """

    def __init__(self, config_path: Path | None = None, timeout: float | None = None) -> None:
        """Store only the path; connection values are loaded for each command.

        :param config_path: Optional SSH configuration path.
        :type config_path: Path | None
        :param timeout: Maximum command execution time in seconds.
        :type timeout: float | None
        """
        if timeout is None:
            timeout = float(os.environ.get("TTL_LAMA_SSH_COMMAND_TIMEOUT", "30"))
        if not math.isfinite(timeout) or timeout <= 0:
            raise ValueError("The SSH command timeout must be positive")
        self._config_path = config_path
        self._timeout = timeout

    def run(
        self, command: Sequence[str],
        *,
        input_data: str | None = None,
    ) -> subprocess.CompletedProcess[str]:
        """Run a command over a new SSH connection.

        :param command: Remote command and arguments.
        :type command: Sequence[str]
        :param input_data: Optional standard input for the remote command.
        :type input_data: str | None
        :returns: The completed SSH process.
        :rtype: subprocess.CompletedProcess[str]
        :raises ValueError: If the command or SSH configuration is invalid.
        :raises subprocess.CalledProcessError: If SSH or the remote command fails.
        :raises FileNotFoundError: If the OpenSSH client is unavailable.
        """
        if isinstance(command, str) or not command:
            raise ValueError("A remote command must contain at least one argument")

        settings = self._load_configuration()
        remote_command = shlex.join(list(command))
        return subprocess.run(
            [
                "ssh",
                "-T",
                "-p",
                str(settings.port),
                "-i",
                str(settings.identity_file),
                "-o",
                "BatchMode=yes",
                "-o",
                "IdentitiesOnly=yes",
                "-o",
                "PasswordAuthentication=no",
                "-o",
                "ForwardAgent=no",
                "-o",
                "StrictHostKeyChecking=yes",
                "-o",
                f"UserKnownHostsFile={settings.known_hosts_file}",
                "-o",
                "GlobalKnownHostsFile=/dev/null",
                "-o",
                f"ConnectTimeout={settings.connection_timeout}",
                "--",
                f"{settings.user}@{settings.host}",
                remote_command,
            ],
            check=True,
            capture_output=True,
            text=True,
            input=input_data,
            timeout=self._timeout,
        )

    def _load_configuration(self) -> SSHConfiguration:
        """Read and validate the SSH settings for the upcoming connection.

        :returns: The validated SSH transport settings.
        :rtype: SSHConfiguration
        :raises ValueError: If the configuration cannot be read or validated.
        """
        config_path = self._config_path or Path(os.environ.get(
            "TTL_LAMA_SSH_CONFIG_FILE",
            "/etc/ttl-lama/ssh_config.yml",
        ))
        try:
            document: object = yaml.safe_load(config_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, yaml.YAMLError) as error:
            raise ValueError("Unable to read the SSH configuration") from error

        if not isinstance(document, dict):
            raise ValueError("The SSH configuration must contain an ssh_config mapping")
        values = cast(dict[str, object], document).get("ssh_config")
        if not isinstance(values, dict):
            raise ValueError("The SSH configuration must contain an ssh_config mapping")
        try:
            return SSHConfiguration.model_validate(values)
        except ValidationError as error:
            raise ValueError("The SSH configuration is invalid") from error
