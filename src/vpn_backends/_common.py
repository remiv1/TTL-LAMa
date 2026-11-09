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
    def reconcile(self, lease: str) -> dict[str, object] | None:
        """Reconcile a VPN lease.
        
        :param lease: The VPN lease to reconcile.
        :type lease: str
        """
        ... # pylint: disable=W2301

    @abstractmethod
    def list_leases(self) -> list[dict[str, object]]:
        """List the peer state currently applied by the backend."""
        ... # pylint: disable=W2301
