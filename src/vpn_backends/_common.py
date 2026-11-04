"""Common VPN backend utilities and base classes.

.. module_author:: Rémi Verschuur <rverschuur@audit-io.fr>
.. version:: 1.0.0
"""
from __future__ import annotations

from abc import ABC, abstractmethod

class VPNBackend(ABC):
    """Abstract base class for VPN backends."""

    @abstractmethod
    def grant(self, lease: str):
        """Grant a VPN lease.
        
        :param lease: The VPN lease to grant.
        :type lease: str
        """
        ... # pylint: disable=W2301

    @abstractmethod
    def revoke(self, lease: str):
        """Revoke a VPN lease.
        
        :param lease: The VPN lease to revoke.
        :type lease: str
        """
        ... # pylint: disable=W2301

    @abstractmethod
    def reconcile(self, lease: str):
        """Reconcile a VPN lease.
        
        :param lease: The VPN lease to reconcile.
        :type lease: str
        """
        ... # pylint: disable=W2301

    @abstractmethod
    def reconcile_all(self) -> None:
        """Reconcile all VPN leases.

        :raises NotImplementedError: If the method is not implemented by the subclass.
        """
        raise NotImplementedError()

    @abstractmethod
    def panic(self):
        """Panic button for VPN backend to revoke all leases immediately."""
        ... # pylint: disable=W2301
