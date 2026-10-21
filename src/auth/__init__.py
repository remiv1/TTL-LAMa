"""Authentification layer isolated from the business logic.

.. classes::
    - `AuthManager`: Manages authentication processes and backends.
    - `User`: Represents an applicative identity exposed to the API, interface, and workflows.

.. module_author:: Rémi Verschuur <rverschuur@audit-io.fr>
.. version:: 1.0.0

.. notes::
    Authentication in TTL-LAMa may have three sources: "none", "internal", and "external".

    - `none`: No authentication is required, the application use a fake or dummy user identity.
    This format is used in small or local application and development environments.
    - `internal`: Authentication is managed internally by the application, typically using a
    local database of user credentials.
    - `external`: Authentication is delegated to an external system, such as an OAuth provider
    or an LDAP server.
"""
from __future__ import annotations

from .manager import AuthManager
from .models import User

__all__ = [
    "AuthManager",
    "User",
]
