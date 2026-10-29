"""Strict request contracts for administrative mutations and filters."""
from __future__ import annotations

from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from api.config.c_profiles import AccessProfile

Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=255)]
Username = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=50)]
Email = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=254)]
Password = Annotated[str, StringConstraints(min_length=1, max_length=1024)]
PublicKey = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=512)]
Duration = Annotated[str, StringConstraints(min_length=1, max_length=255)]
Identifier = Annotated[int, Field(gt=0)]


class Input(BaseModel):
    """Reject unknown fields and coercion in JSON bodies."""
    model_config = ConfigDict(extra="forbid", strict=True)


class UserCreate(Input):
    """Create a local identity, optionally with internal credentials."""
    username: Username
    email: Email | None = None
    enabled: bool = True
    is_admin: bool = False
    password: Password | None = None


class UserPatch(Input):
    """Only supplied fields are updated; only email may explicitly be null."""
    username: Username | None = None
    email: Email | None = None
    enabled: bool | None = None
    is_admin: bool | None = None
    password: Password | None = None


class DevicePatch(Input):
    """Device ownership and lifecycle fields cannot be reassigned."""
    name: Name | None = None
    public_key: PublicKey | None = None


class ProfileCreate(AccessProfile):
    """A complete profile policy."""
    name: Name
    default_duration: Duration
    maximum_duration: Duration


class ProfilePatch(Input):
    """Policy fields are validated together after merging persisted values."""
    name: Name | None = None
    default_duration: Duration | None = None
    maximum_duration: Duration | None = None
    networks: list[str] | None = Field(default=None, min_length=1)


class Filters(BaseModel):
    """Query-string values may be parsed, but unknown filters are rejected."""
    model_config = ConfigDict(extra="forbid")


class UserFilters(Filters):
    device: Identifier | None = None
    lease: Identifier | None = None
    profile: Identifier | None = None


class DeviceFilters(Filters):
    lease: Identifier | None = None
    profile: Identifier | None = None


class LeaseFilters(Filters):
    user: UUID | None = None
    device: Identifier | None = None
    profile: Identifier | None = None
    status: Literal["active", "expired", "revoked"] | None = None


class ProfileFilters(Filters):
    user: UUID | None = None
    device: Identifier | None = None
    lease: Identifier | None = None
