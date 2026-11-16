# TTL-LAMa Installer

Download the latest installer package without cloning the repository:

```sh
wget https://github.com/remiv1/ttl-lama/releases/latest/download/ttlama-installer.tar.gz
wget https://github.com/remiv1/ttl-lama/releases/latest/download/ttlama-installer.tar.gz.sha256
sha256sum -c ttlama-installer.tar.gz.sha256
tar -xzf ttlama-installer.tar.gz
cd ttlama-installer-*
python3 -m venv .venv
.venv/bin/python -m pip install -r scripts/install/requirements.txt
PYTHON=.venv/bin/python scripts/install/install.sh
```

To retrieve a specific version, replace `latest` in the download URLs with its release tag and use the matching versioned archive name.

The installer generates configuration files and displays the Podman commands; it does not execute them. Review those commands before running them. The application image must already be available on the host.

WireGuard profiles declare their interface, destinations, durations, public endpoint, server public key and client address pools. Profiles sharing an interface must use matching connection settings. The first usable address of each pool is reserved for the router; the remaining addresses are allocated persistently per device/interface.

The installer prints nftables integration proposals on stdout and offers to include them as comments in the VPN host preparation script. It never applies these rules or executes that script. The router administrator must review and integrate the proposals into the existing firewall. TTL-LAMa never reads or changes nftables during lease or peer operations. Client-side AllowedIPs alone do not enforce profile destination restrictions.

The former interface-based configuration and previous database schemas are not converted or migrated. No existing data is automatically removed.
