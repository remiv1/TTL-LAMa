"""Available Implementations of authentication backends.

.. classes::
    - `AuthBackend`: Base class for all authentication backends.
    - `InternalAuthBackend`: Backend for internal authentication.
    - `OIDCAuthBackend`: Backend for OpenID Connect (OIDC) authentication.

.. module_author:: Rémi Verschuur <rverschuur@audit-io.fr>
.. version:: 1.0.0
"""
from __future__ import annotations

from .base import AuthBackend
from .internal import InternalAuthBackend
from .oidc import OIDCAuthBackend

__all__ = [
    "AuthBackend",
    "InternalAuthBackend",
    "OIDCAuthBackend",
]
