"""Wireguard VPN backend implementation.

.. classes::
    - `WireGuardBackend`: Wireguard VPN backend implementation.
    
.. module_author:: Rémi Verschuur <rverschuur@audit-io.fr>
.. version:: 1.0.0
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import cast

from scheduler.ssh import SSHCommandExecutor

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
    def __init__(
        self,
        config: WireGuardConfig | None = None,
        executor: SSHCommandExecutor | None = None,
    ) -> None:
        self.config = config
        self.executor = executor or SSHCommandExecutor()
        super().__init__()

    def _run(self, operation: str, lease: str | None = None, *, interface: str = "all") -> object:
        command = ["sudo", "-n", "ttlama", "backend", "wg", "leases", operation]
        if lease is not None:
            command.extend(["--lease", "-"])
        elif operation == "ls":
            command.extend(["--interface", interface])
        if operation in ("get", "ls"):
            command.append("--json")
        result = self.executor.run(command, input_data=lease)
        try:
            return json.loads(result.stdout)
        except (ValueError, TypeError) as error:
            raise RuntimeError("Invalid JSON response from the WireGuard backend") from error

    def grant(self, lease: str) -> None:
        """Grant a Wireguard VPN lease.
        
        :param lease: The VPN lease to grant.
        :type lease: str
        """
        result = self._run("apply", lease)
        if (
            not isinstance(result, dict)
            or cast(dict[str, object], result).get("success") is not True
        ):
            raise RuntimeError("WireGuard backend did not confirm the apply operation")

    def revoke(self, lease: str) -> None:
        """Revoke a Wireguard VPN lease.
        
        :param lease: The VPN lease to revoke.
        :type lease: str
        """
        result = self._run("delete", lease)
        if (
            not isinstance(result, dict)
            or cast(dict[str, object], result).get("success") is not True
        ):
            raise RuntimeError("WireGuard backend did not confirm the delete operation")

    def reconcile(self, lease: str) -> dict[str, object] | None:
        """Reconcile a Wireguard VPN lease.
        
        :param lease: The VPN lease to reconcile.
        :type lease: str
        """
        result = self._run("get", lease)
        if result is not None and not isinstance(result, dict):
            raise RuntimeError("Invalid WireGuard lease response")
        return cast(dict[str, object] | None, result)

    def list_leases(self, interface: str = "all") -> list[dict[str, object]]:
        """List peers on a WireGuard interface.

        :param interface: Interface name, or ``all``.
        :type interface: str
        :returns: The peer states returned by the backend.
        :rtype: list[dict[str, object]]
        """
        result = self._run("ls", interface=interface)
        if not isinstance(result, list):
            raise RuntimeError("Invalid WireGuard lease list response")
        items = cast(list[object], result)
        if not all(isinstance(item, dict) for item in items):
            raise RuntimeError("Invalid WireGuard lease list response")
        return cast(list[dict[str, object]], items)

    def reconcile_all(self) -> None:
        """Reconcile all Wireguard VPN leases.
        
        :raises NotImplementedError: If the method is not implemented.
        """
        raise NotImplementedError("Automatic reconciliation is not implemented")

    def panic(self) -> None:
        """Panic button for Wireguard VPN backend to revoke all leases immediately."""
        raise NotImplementedError("Bulk revocation is not implemented")
