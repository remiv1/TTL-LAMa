"""Pydantic and enum definitions for authentication methods.

.. module_author:: Rémi Verschuur <rverschuur@audit-io.fr>
.. version:: 1.0
"""
from __future__ import annotations

from enum import Enum

class AuthMethod(str, Enum):
    """Enumeration of authentication methods.
    
    .. INTERNAL::
        - type: str
        - values: "internal"
    
    .. EXTERNAL::
        - type: str
        - values: "external"

    .. OIDC::
        - type: str
        - values: "oidc"
    """

    INTERNAL = "internal"
    EXTERNAL = "external"
    OIDC = "oidc"
