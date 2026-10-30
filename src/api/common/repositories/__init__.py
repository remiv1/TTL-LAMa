"""Module providing transaction-neutral repositories for API and configuration consumers.

.. classes::
    - `ConflictError`: Raised when a conflict occurs in the repository.
    - `NotFoundError`: Raised when an entity is not found in the repository.
    - `DeviceRepository`: Repository for managing devices.
    - `LeaseRepository`: Repository for managing leases.
    - `ProfileRepository`: Repository for managing profiles.
    - `UserRepository`: Repository for managing users.

.. module_author:: Rémi Verschuur <rverschuur@audit-io.fr>
.. version:: 1.0.0
"""

from .base import ConflictError, NotFoundError
from .devices import DeviceRepository
from .leases import LeaseRepository
from .profiles import ProfileRepository
from .users import UserRepository

__all__ = [
    "ConflictError",
    "NotFoundError",
    "DeviceRepository",
    "LeaseRepository",
    "ProfileRepository",
    "UserRepository",
]
