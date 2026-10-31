"""Password change request body model for self-service password changes.

.. module_author:: Rémi Verschuur <rverschuur@audit-io.fr>
.. version:: 1.0.0
"""
from __future__ import annotations

from typing import Annotated

from pydantic import BaseModel, ConfigDict, StringConstraints

Password = Annotated[str, StringConstraints(min_length=1, max_length=1024)]

class PasswordChange(BaseModel):
    """Strict request body for self-service password changes."""

    model_config = ConfigDict(extra="forbid", strict=True)

    current_password: Password
    new_password: Password
