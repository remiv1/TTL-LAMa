"""Authentification layer isolated from the business logic.

.. classes::
    - `AuthManager`: Manages authentication processes and backends.
    - `User`: Represents an applicative identity exposed to the API, interface, and workflows.

.. module_author:: Rémi Verschuur <rverschuur@audit-io.fr>
.. version:: 1.0.0

.. note::
    Authentication is always required. It is managed internally or delegated to an
    external identity provider.
"""
from __future__ import annotations

#from .manager import AuthManager
#from .models import User

__all__ = [
    #"AuthManager",
    #"User",
]
