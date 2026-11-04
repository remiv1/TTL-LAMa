"""Wireguard VPN backend implementation.

.. classes::
    - `WireGuardBackend`: Wireguard VPN backend implementation.
    
.. module_author:: Rémi Verschuur <rverschuur@audit-io.fr>
.. version:: 1.0.0
"""
from __future__ import annotations

from dataclasses import dataclass

from ._common import VPNBackend

@dataclass
class WireGuardConfig:
    """Wireguard VPN backend configuration.
    
    :param name: The name of the Wireguard VPN backend.
    :type name: str
    :param private_key: The private key for the Wireguard VPN backend.
    :type private_key: str
    :param public_key: The public key for the Wireguard VPN backend.
    :type public_key: str
    """
    name: str
    private_key: str
    public_key: str


class WireGuardBackend(VPNBackend):
    """Wireguard VPN backend implementation.

    :param config: The Wireguard VPN backend configuration.
    :type config: WireGuardConfig
    """
    def __init__(self, config: WireGuardConfig):
        self.config = config
        super().__init__()

    def grant(self, lease: str):
        """Grant a Wireguard VPN lease.
        
        :param lease: The VPN lease to grant.
        :type lease: str
        """
        ... # pylint: disable=W2301

    def revoke(self, lease: str):
        """Revoke a Wireguard VPN lease.
        
        :param lease: The VPN lease to revoke.
        :type lease: str
        """
        ... # pylint: disable=W2301

    def reconcile(self, lease: str):
        """Reconcile a Wireguard VPN lease.
        
        :param lease: The VPN lease to reconcile.
        :type lease: str
        """
        ... # pylint: disable=W2301

    def reconcile_all(self):
        """Reconcile all Wireguard VPN leases.
        
        :raises NotImplementedError: If the method is not implemented.
        """
        ... # pylint: disable=W2301

    def panic(self):
        """Panic button for Wireguard VPN backend to revoke all leases immediately."""
        ... # pylint: disable=W2301
