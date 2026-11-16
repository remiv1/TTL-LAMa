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

To retrieve a specific version, replace `latest` in the download URLs with its
release tag and use the matching versioned archive name.

The installer generates configuration files and displays the Podman commands;
it does not execute them. Review those commands before running them. The
application image must already be available on the host.
