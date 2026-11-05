"""Validation of declarative access profiles.

.. classes::
    - `AccessPolicy`: Access rules constrained by a duration and allowed networks.
    - `AccessProfile`: Access policy assigned to a backend lease target.
    - `AccessProfiles`: Collection of persisted profile policies.
    - `BackendConfig`: Backend interfaces loaded from a YAML file.

.. functions::
    - `parse_duration`: Convert a compact duration into a Python duration.

.. module_author:: Rémi Verschuur <rverschuur@audit-io.fr>
.. version:: 1.0.0
"""
from __future__ import annotations

import re
from datetime import timedelta
from ipaddress import ip_network
from pathlib import Path
from typing import cast

import yaml
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    IPvAnyNetwork,
    field_validator,
    model_validator,
)

_DURATION_PART = re.compile(r"(\d+)([dhms])")
_DURATION_UNITS = {
    "d": 24 * 60 * 60,
    "h": 60 * 60,
    "m": 60,
    "s": 1,
}


def parse_duration(value: str) -> timedelta:
    """Convert a compact duration string to a :class:`datetime.timedelta`.

    :param value: Duration composed of ``d``, ``h``, ``m``, or ``s`` units.
    :type value: str
    :returns: The converted duration.
    :rtype: datetime.timedelta
    :raises ValueError: If the value is empty, malformed, or zero.

    """
    matches = list(_DURATION_PART.finditer(value))
    if not matches or "".join(match.group(0) for match in matches) != value:
        raise ValueError("La durée doit utiliser les unités d, h, m ou s")
    seconds = sum(
        int(match.group(1)) * _DURATION_UNITS[match.group(2)]
        for match in matches
    )
    if seconds <= 0:
        raise ValueError("La durée doit être supérieure à zéro")
    return timedelta(seconds=seconds)


class AccessPolicy(BaseModel):
    """Access policy bounded by a duration and a set of allowed networks.

    .. author:: Rémi Verschuur <rverschuur@audit-io.fr>
    .. version:: 1.0.0
    """

    model_config = ConfigDict(extra="forbid")

    default_duration: str
    maximum_duration: str
    networks: list[IPvAnyNetwork] = Field(min_length=1)

    @field_validator("networks", mode="before")
    @classmethod
    def normalize_networks(cls, value: object) -> object:
        """Normalize CIDRs to their containing network.

        :param value: The configured network values.
        :type value: object
        :returns: The network values normalized to their network address.
        :rtype: object
        """
        if not isinstance(value, list):
            return value
        networks = cast(list[str | IPvAnyNetwork], value)
        return [
            ip_network(network, strict=False) if isinstance(network, str) else network
            for network in networks
        ]

    @model_validator(mode="after")
    def validate_durations(self) -> AccessPolicy:
        """Reject a default duration greater than the profile maximum.

        :returns: The validated access profile.
        :rtype: AccessPolicy
        :raises ValueError: If the default duration exceeds the maximum duration.
        """
        if parse_duration(self.default_duration) > parse_duration(self.maximum_duration):
            raise ValueError(
                "La durée par défaut ne peut pas dépasser la durée maximale"
            )
        return self


class AccessProfile(AccessPolicy):
    """Access policy assigned to a configured backend target.

    :param lease_target: The backend target to which this access profile applies.
    :type lease_target: str

    .. author:: Rémi Verschuur <rverschuur@audit-io.fr>
    .. version:: 1.0.0
    """
    lease_target: str = Field(min_length=1, max_length=255)


class AccessProfiles(BaseModel):
    """Collection of validated access profile policies.

    :param profiles: The dictionary of access profiles keyed by their names.
    :type profiles: dict[str, AccessProfile]

    .. author:: Rémi Verschuur <rverschuur@audit-io.fr>
    .. version:: 1.0.0
    """
    model_config = ConfigDict(extra="forbid")

    profiles: dict[str, AccessProfile] = Field(default_factory=dict)


class WireGuardInterface(AccessPolicy):
    """WireGuard interface settings that define an access profile.

    :param name: The name of the WireGuard interface.
    :type name: str
    :param description: The description of the WireGuard interface.
    :type description: str
    :param public_key: The public key of the WireGuard interface.
    :type public_key: str

    .. author:: Rémi Verschuur <rverschuur@audit-io.fr>
    .. version:: 1.0.0
    """

    name: str = Field(min_length=1, max_length=255)
    description: str = ""
    public_key: str = Field(min_length=1, max_length=512)


class WireGuardBackend(BaseModel):
    """WireGuard backend settings.

    :param interfaces: The list of WireGuard interfaces for the backend.
    :type interfaces: list[WireGuardInterface]

    .. author:: Rémi Verschuur <rverschuur@audit-io.fr>
    .. version:: 1.0.0
    """

    model_config = ConfigDict(extra="forbid")

    interfaces: list[WireGuardInterface] = Field(min_length=1)


class BackendSection(BaseModel):
    """Configured VPN backend implementations.

    :param wireguard: The WireGuard backend configuration.
    :type wireguard: WireGuardBackend

    .. author:: Rémi Verschuur <rverschuur@audit-io.fr>
    .. version:: 1.0.0
    """

    model_config = ConfigDict(extra="forbid")

    wireguard: WireGuardBackend


class BackendConfig(BaseModel):
    """Validated backend configuration and its profile mappings.

    :param backend: The backend section containing VPN backend configurations.
    :type backend: BackendSection

    .. author:: Rémi Verschuur <rverschuur@audit-io.fr>
    .. version:: 1.0.0
    """

    model_config = ConfigDict(extra="forbid")

    backend: BackendSection

    @classmethod
    def from_file(cls, path: Path | None) -> BackendConfig | None:
        """Load and validate backend settings from a YAML file.

        :param path: File path, or ``None`` to disable backend configuration.
        :type path: Path | None
        :returns: The validated backend configuration, or ``None`` when no file is set.
        :rtype: BackendConfig | None
        :raises OSError: If the configured file cannot be read.
        :raises ValueError: If the YAML document is not a mapping.

        """
        if path is None:
            return None
        with path.open(encoding="utf-8") as config_file:
            document = yaml.safe_load(config_file)
        if not isinstance(document, dict):
            raise ValueError("The backend configuration must contain a YAML mapping")
        return cls.model_validate(document)

    @model_validator(mode="after")
    def validate_unique_interfaces(self) -> BackendConfig:
        """Reject duplicate interface targets and profile names.

        :returns: The validated backend configuration.
        :rtype: BackendConfig
        :raises ValueError: If an interface target or profile name is duplicated.
        """
        interfaces = self.backend.wireguard.interfaces
        targets = [interface.name for interface in interfaces]
        profile_names = [
            interface.description.strip() or interface.name
            for interface in interfaces
        ]
        if len(targets) != len(set(targets)):
            raise ValueError("WireGuard interface names must be unique")
        if len(profile_names) != len(set(profile_names)):
            raise ValueError("Backend interface descriptions must be unique")
        return self

    @property
    def lease_targets(self) -> set[str]:
        """Return the configured backend interface names.

        :returns: The interface names that can receive leases.
        :rtype: set[str]
        """
        return {interface.name for interface in self.backend.wireguard.interfaces}

    @property
    def access_profiles(self) -> AccessProfiles:
        """Convert configured interfaces into persisted profile policies.

        :returns: Profiles keyed by interface description, falling back to interface name.
        :rtype: AccessProfiles
        """
        profiles = {
            interface.description.strip() or interface.name: AccessProfile(
                lease_target=interface.name,
                default_duration=interface.default_duration,
                maximum_duration=interface.maximum_duration,
                networks=interface.networks,
            )
            for interface in self.backend.wireguard.interfaces
        }
        return AccessProfiles(profiles=profiles)
