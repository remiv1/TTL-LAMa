"""Common other objects for the API.

.. module_author:: Rémi Verschuur <rverschuur@audit-io.fr>
.. version:: 1.0
"""
from __future__ import annotations

from .auth_methods import AuthMethod
from .passwords import PasswordChange, Password

__all__ = [
    "AuthMethod",
    "PasswordChange",
    "Password",
]
