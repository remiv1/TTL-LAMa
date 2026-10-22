"""Validation of declarative access profiles.

.. classes::
    - `AccessProfile`: Access policy constrained by a duration and allowed networks.
    - `AccessProfiles`: Collection of profiles loaded from a YAML file.

.. functions::
    - `parse_duration`: Convert a compact duration into a Python duration.

.. module_author:: Rémi Verschuur <rverschuur@audit-io.fr>
.. version:: 1.0.0
"""
from __future__ import annotations

import re
from datetime import timedelta
from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field, IPvAnyNetwork, model_validator

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


class AccessProfile(BaseModel):
    """Access policy bounded by a duration and a set of allowed networks.

    .. author:: Rémi Verschuur <rverschuur@audit-io.fr>
    .. version:: 1.0.0
    """

    model_config = ConfigDict(extra="forbid")

    default_duration: str
    maximum_duration: str
    networks: list[IPvAnyNetwork] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_durations(self) -> AccessProfile:
        """Reject a default duration greater than the profile maximum.

        :returns: The validated access profile.
        :rtype: AccessProfile
        :raises ValueError: If the default duration exceeds the maximum duration.
        """
        if parse_duration(self.default_duration) > parse_duration(self.maximum_duration):
            raise ValueError(
                "La durée par défaut ne peut pas dépasser la durée maximale"
            )
        return self


class AccessProfiles(BaseModel):
    """Collection of access profiles declared in a YAML file.

    .. author:: Rémi Verschuur <rverschuur@audit-io.fr>
    .. version:: 1.0.0
    """

    model_config = ConfigDict(extra="forbid")

    profiles: dict[str, AccessProfile] = Field(default_factory=dict)

    @classmethod
    def from_file(cls, path: Path | None) -> AccessProfiles:
        """Load and validate access profiles from a YAML file.

        :param path: File path, or ``None`` to disable profile configuration.
        :type path: Path | None
        :returns: The validated profiles, or an empty collection when no file is set.
        :rtype: AccessProfiles
        :raises OSError: If the configured file cannot be read.
        :raises ValueError: If the YAML document is not a mapping.

        """
        if path is None:
            return cls()
        with path.open(encoding="utf-8") as config_file:
            document = yaml.safe_load(config_file)
        if document is None:
            document = {}
        if not isinstance(document, dict):
            raise ValueError("The access-profile file must contain a YAML mapping")
        return cls.model_validate(document)
