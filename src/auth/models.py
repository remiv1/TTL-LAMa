"""Uniform applicative identity, independent of the backend and SQL models.

.. classes::
    - `User`: Represents an applicative identity exposed to the API, interface, and workflows.
    - `UserUpdate`: Describes the fields to change on an existing user.
    - `ExternalUserIdentity`: Contains normalized identity-provider claims.

.. module_author:: Rémi Verschuur <rverschuur@audit-io.fr>
.. version:: 1.0.0
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True, slots=True)
class UserUpdate:
    """Data describing requested changes to an existing user.

    :param user_id: The database identifier of the user to update.
    :type user_id: int
    :param username: Optional replacement username.
    :type username: str | None
    :param email: Optional replacement email address.
    :type email: str | None
    :param password: Optional replacement password.
    :type password: str | None
    :param group_names: Optional replacement group names.
    :type group_names: list[str] | None
    :param enabled: Optional account-enabled state.
    :type enabled: bool | None

    .. author:: Rémi Verschuur <rverschuur@audit-io.fr>
    .. version:: 1.0.0
    """

    user_id: int
    username: str | None = None
    email: str | None = None
    password: str | None = None
    group_names: list[str] | None = None
    enabled: bool | None = None


@dataclass(frozen=True, slots=True)
class ExternalUserIdentity:
    """Normalized identity-provider data used to synchronize a local user.

    :param issuer: The identity provider issuer.
    :type issuer: str
    :param subject: The stable subject identifier from the provider.
    :type subject: str
    :param username: The generated local username.
    :type username: str
    :param email: The generated local email placeholder.
    :type email: str
    :param group_names: The allowed local groups requested by the provider.
    :type group_names: frozenset[str]
    """

    issuer: str
    subject: str
    username: str
    email: str
    group_names: frozenset[str]


@dataclass(frozen=True, slots=True)
class User:
    """Applicative identity exposed to the API, interface, and workflows.

    :param id: The unique identifier of the user.
    :type id: int | str
    :param username: The username of the user.
    :type username: str
    :param groups: The groups the user belongs to.
    :type groups: list[str]
    :param auth_source: The authentication source of the user.
    :type auth_source: Literal["internal", "external"]
    :raises ValueError: If any of the parameters are invalid.

    .. methods::
        - `to_dict`: Convert the user identity to a dictionary compatible with JSON.

    .. author:: Rémi Verschuur <rverschuur@audit-io.fr>
    .. version:: 1.0.0
    """

    id: int | str
    username: str
    groups: list[str]
    auth_source: Literal["internal", "external"]

    def to_dict(self) -> dict[str, int | str | list[str]]:
        """Return the user identity as a JSON-compatible dictionary.
        
        :return: A dictionary representation of the user identity.
        :rtype: dict[str, int | str | list[str]]
        """
        return {
			"id": self.id,
			"username": self.username,
			"groups": self.groups,
			"auth_source": self.auth_source,
		}
