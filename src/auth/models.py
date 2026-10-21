"""Uniform applicative identity, independent of the backend and SQL models.

.. classes::
    - `User`: Represents an applicative identity exposed to the API, interface, and workflows.

.. module_author:: Rémi Verschuur <rverschuur@audit-io.fr>
.. version:: 1.0.0
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

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
    :type auth_source: Literal["none", "internal", "external"]
    :raises ValueError: If any of the parameters are invalid.

    .. methods::
        - `to_dict`: Convert the user identity to a dictionary compatible with JSON.

    .. author:: Rémi Verschuur <rverschuur@audit-io.fr>
    .. version:: 1.0.0
    """

    id: int | str
    username: str
    groups: list[str]
    auth_source: Literal["none", "internal", "external"]

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
