"""Strict request contracts for administrative mutations and filters.

.. classes::
    - `Input`: Base class for all input schemas, rejecting unknown fields and coercion.
    - `UserCreate`: Schema for creating a new user.
    - `UserPatch`: Schema for updating an existing user.
    - `DevicePatch`: Schema for updating a device.
    - `ProfileCreate`: Schema for creating a new profile.
    - `ProfilePatch`: Schema for updating an existing profile.
    - `Filters`: Base class for all filter schemas.
    - `UserFilters`: Schema for filtering users.
    - `DeviceFilters`: Schema for filtering devices.
    - `LeaseFilters`: Schema for filtering leases.
    - `ProfileFilters`: Schema for filtering profiles.
"""
from __future__ import annotations

from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

from api.config.c_profiles import AccessProfile

Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=255)]
Username = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=50)]
Email = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=254)]
Password = Annotated[str, StringConstraints(min_length=1, max_length=1024)]
PublicKey = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=512)]
Duration = Annotated[str, StringConstraints(min_length=1, max_length=255)]
Identifier = Annotated[int, Field(gt=0)]


class Input(BaseModel):
    """Reject unknown fields and coercion in JSON bodies.
    
    .. values::
        - `model_config`: Pydantic model configuration for the schema.

    .. author:: Rémi Verschuur <rverschuur@audit-io.fr>
    .. version:: 1.0.0
    """
    model_config = ConfigDict(extra="forbid", strict=True)


class OIDCLink(Input):
    """Identify an external OIDC account by its issuer and subject.

    :param issuer: The exact issuer URL from the identity provider.
    :type issuer: str
    :param subject: The stable subject identifier from the identity provider.
    :type subject: str

    .. author:: Rémi Verschuur <rverschuur@audit-io.fr>
    .. version:: 1.0.0
    """

    issuer: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=255)]
    subject: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=255)]


def _validate_unique_oidc_links(links: list[OIDCLink]) -> None:
    identities = [(link.issuer, link.subject) for link in links]
    if len(identities) != len(set(identities)):
        raise ValueError("OIDC identities must not be repeated")


def _empty_oidc_links() -> list[OIDCLink]:
    return []


class UserCreate(Input):
    """Create a local identity, optionally with internal credentials.
    
    .. values::
        - `username`: The username of the user.
        - `email`: The email address of the user.
        - `enabled`: Whether the user is enabled.
        - `is_admin`: Whether the user has administrative privileges.
        - `password`: The password for the user.
        - `oidc_links`: External OIDC identities linked to the user.

    .. author:: Rémi Verschuur <rverschuur@audit-io.fr>
    .. version:: 1.0.0
    """
    username: Username
    email: Email | None = None
    enabled: bool = True
    is_admin: bool = False
    password: Password | None = None
    oidc_links: list[OIDCLink] = Field(default_factory=_empty_oidc_links)

    @model_validator(mode="after")
    def validate_oidc_links(self) -> UserCreate:
        """Validate that OIDC links are unique and not repeated.

        :return: The validated UserCreate instance.
        :rtype: UserCreate
        :raises ValueError: If any OIDC identity is repeated.
        """
        _validate_unique_oidc_links(self.oidc_links)
        return self


class UserPatch(Input):
    """Only supplied fields are updated; only email may explicitly be null.
    
    .. values::
        - `username`: The username of the user.
        - `email`: The email address of the user.
        - `enabled`: Whether the user is enabled.
        - `is_admin`: Whether the user has administrative privileges.
        - `password`: The password for the user.
        - `link_oidc`: OIDC identities to link to the user.
        - `unlink_oidc`: OIDC identities to unlink from the user.

    .. author:: Rémi Verschuur <rverschuur@audit-io.fr>
    .. version:: 1.0.0
    """
    username: Username | None = None
    email: Email | None = None
    enabled: bool | None = None
    is_admin: bool | None = None
    password: Password | None = None
    link_oidc: list[OIDCLink] = Field(default_factory=_empty_oidc_links)
    unlink_oidc: list[OIDCLink] = Field(default_factory=_empty_oidc_links)

    @model_validator(mode="after")
    def validate_oidc_changes(self) -> UserPatch:
        """Validate that OIDC changes are consistent.

        :return: The validated UserPatch instance.
        :rtype: UserPatch
        :raises ValueError: If any OIDC identity is repeated or conflicting.
        """
        _validate_unique_oidc_links(self.link_oidc)
        _validate_unique_oidc_links(self.unlink_oidc)
        linked = {(link.issuer, link.subject) for link in self.link_oidc}
        unlinked = {(link.issuer, link.subject) for link in self.unlink_oidc}
        if linked & unlinked:
            raise ValueError("An OIDC identity cannot be linked and unlinked together")
        return self


class DevicePatch(Input):
    """Device ownership and lifecycle fields cannot be reassigned.

    .. values::
        - `name`: The name of the device.
        - `public_key`: The public key of the device.

    .. author:: Rémi Verschuur <rverschuur@audit-io.fr>
    .. version:: 1.0.0
    """
    name: Name | None = None
    public_key: PublicKey | None = None


class ProfileCreate(AccessProfile):
    """A complete profile policy.
    
    .. values::
        - `name`: The name of the profile.
        - `default_duration`: The default duration for the profile.
        - `maximum_duration`: The maximum duration for the profile.

    .. author:: Rémi Verschuur <rverschuur@audit-io.fr>
    .. version:: 1.0.0
    """
    name: Name
    default_duration: Duration
    maximum_duration: Duration


class ProfilePatch(Input):
    """Policy fields are validated together after merging persisted values.

    .. values::
        - `name`: The name of the profile.
        - `default_duration`: The default duration for the profile.
        - `maximum_duration`: The maximum duration for the profile.
        - `networks`: The list of networks associated with the profile.

    .. author:: Rémi Verschuur <rverschuur@audit-io.fr>
    .. version:: 1.0.0
    """
    name: Name | None = None
    default_duration: Duration | None = None
    maximum_duration: Duration | None = None
    networks: list[str] | None = Field(default=None, min_length=1)


class Filters(BaseModel):
    """Query-string values may be parsed, but unknown filters are rejected.

    .. values::
        - `model_config`: The configuration of the model.

    .. author:: Rémi Verschuur <rverschuur@audit-io.fr>
    .. version:: 1.0.0
    """
    model_config = ConfigDict(extra="forbid")


class UserFilters(Filters):
    """Filters for querying users.

    .. values::
        - `device`: The identifier of the device.
        - `lease`: The identifier of the lease.
        - `profile`: The identifier of the profile.

    .. author:: Rémi Verschuur <rverschuur@audit-io.fr>
    .. version:: 1.0.0
    """
    device: Identifier | None = None
    lease: Identifier | None = None
    profile: Identifier | None = None


class DeviceFilters(Filters):
    """Filters for querying devices.

    .. values::
        - `lease`: The identifier of the lease.
        - `profile`: The identifier of the profile.

    .. author:: Rémi Verschuur <rverschuur@audit-io.fr>
    .. version:: 1.0.0
    """
    lease: Identifier | None = None
    profile: Identifier | None = None


class LeaseFilters(Filters):
    """Filters for querying leases.

    .. values::
        - `user`: The identifier of the user.
        - `device`: The identifier of the device.
        - `profile`: The identifier of the profile.
        - `status`: The status of the lease.

    .. author:: Rémi Verschuur <rverschuur@audit-io.fr>
    .. version:: 1.0.0
    """
    user: UUID | None = None
    device: Identifier | None = None
    profile: Identifier | None = None
    status: Literal["active", "expired", "revoked"] | None = None


class ProfileFilters(Filters):
    """Filters for querying profiles.

    .. values::
        - `user`: The identifier of the user.
        - `device`: The identifier of the device.
        - `lease`: The identifier of the lease.

    .. author:: Rémi Verschuur <rverschuur@audit-io.fr>
    .. version:: 1.0.0
    """
    user: UUID | None = None
    device: Identifier | None = None
    lease: Identifier | None = None


class DeviceCreate(Input):
    """Strict input schema for creating an owned device."""

    name: Name
    public_key: PublicKey


class LeaseCreate(Input):
    """Strict input schema for requesting a lease from an assigned profile."""

    device_id: Identifier
    profile_id: Identifier
    duration: Duration | None = Field(default=None)
