"""Generate configuration and installation artifacts for TTL-LAMa.

.. functions::
    - ``main``: Run the interactive installer configuration flow.

.. constants::
    - ``INSTALL_CONFIG_PATH``: Host path containing files mounted under ``/etc/ttl-lama``.
    - ``INSTALL_SECRETS_PATH``: Host path containing files mounted under ``/run/secrets``.
    - ``INSTALL_VPN_PATH``: Host path containing VPN host setup artifacts.

.. module_author:: Rémi Verschuur <rverschuur@audit-io.fr>
.. version:: 1.0.0
""" # pylint: disable=C0302
from __future__ import annotations

import argparse
import copy
import getpass
import ipaddress
import os
import re
import secrets
import shlex
import shutil
import subprocess
import sys
import tempfile
import uuid
from pathlib import Path
from typing import Any

import yaml

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPOSITORY_ROOT / "src"))

from api.config.c_profiles import BackendConfig, parse_duration  # pylint: disable=C0413
from api.config.global_config import redact_secrets, validate_configuration  # pylint: disable=C0413
from scheduler.ssh import SSHConfiguration  # pylint: disable=C0413

CONTAINER_CONFIG = "/etc/ttl-lama/config.yml"
CONTAINER_BACKEND_CONFIG = "/etc/ttl-lama/backend_config.yml"
CONTAINER_SSH_CONFIG = "/etc/ttl-lama/ssh_config.yml"
CONTAINER_KNOWN_HOSTS = "/etc/ttl-lama/ssh_known_hosts"
CONTAINER_SECRETS = "/run/secrets"
DEFAULT_CLI_PATH = "/opt/ttl-lama-cli/bin/ttlama"
WRAPPER_PATH = "/usr/local/sbin/ttlama-ssh-wrapper"
VPN_HOST_SETUP_FILE = "vpn-host-setup.sh"
VOLUME_MOUNT_PREFIX = "  -v "
WIREGUARD_PUBLIC_KEY_PLACEHOLDER = "REPLACE_WITH_WIREGUARD_PUBLIC_KEY"
INSTALL_CONFIG_PATH = Path("etc/ttl-lama")
INSTALL_SECRETS_PATH = Path("run/secrets")
INSTALL_VPN_PATH = Path("opt/ttl-lama-vpn")


def _unique_output_directory(output_dir: Path) -> Path:
    if not output_dir.name:
        raise ValueError("The output directory cannot be a filesystem root.")
    if not os.path.lexists(output_dir):
        return output_dir
    while True:
        candidate = output_dir.with_name(f"{output_dir.name}-{uuid.uuid4().hex[:8]}")
        if not os.path.lexists(candidate):
            return candidate


def print_section(title: str, guidance: str) -> None:
    """Print a section header and guidance text.

    :param title: The title of the section.
    :type title: str
    :param guidance: The guidance text to display under the title.
    :type guidance: str
    """
    print(f"\n=== {title} ===")
    print(guidance)


def ask_text(prompt: str, default: str | None = None, secret: bool = False) -> str:
    """Ask the user for a text input.

    :param prompt: The prompt to display to the user.
    :type prompt: str
    :param default: The default value if the user provides no input.
    :type default: str | None
    :param secret: Whether the input should be hidden (for passwords).
    :type secret: bool

    :return: The user's input, or the default if no input was provided.
    :rtype: str
    """
    label = f"{prompt} [{default}]: " if default is not None else f"{prompt}: "
    while True:
        value = getpass.getpass(label) if secret else input(label)
        if not value and default is not None:
            value = default
        if value and (secret or value.strip()):
            return value if secret else value.strip()
        print("A value is required.")


def ask_choice(prompt: str, choices: list[str], default: str) -> str:
    """Ask the user to choose from a list of options.

    :param prompt: The prompt to display to the user.
    :type prompt: str
    :param choices: A list of valid choices.
    :type choices: list[str]
    :param default: The default value if the user provides no input.
    :type default: str

    :return: The user's chosen option.
    :rtype: str
    """
    options = "/".join(choices)
    normalized_choices = {choice.lower(): choice for choice in choices}
    while True:
        value = input(f"{prompt} ({options}) [{default}]: ").strip().lower() or default.lower()
        if value in normalized_choices:
            return normalized_choices[value]
        print(f"Choose one of: {options}.")


def ask_bool(prompt: str, default: bool) -> bool:
    """Ask the user for a yes/no input.

    :param prompt: The prompt to display to the user.
    :type prompt: str
    :param default: The default value if the user provides no input.
    :type default: bool

    :return: The user's choice as a boolean.
    :rtype: bool
    """
    default_text = "yes" if default else "no"
    while True:
        value = input(f"{prompt} (yes/no) [{default_text}]: ").strip().lower() or default_text
        if value in {"y", "yes"}:
            return True
        if value in {"n", "no"}:
            return False
        print("Answer yes or no.")


def ask_int(prompt: str, default: int, minimum: int, maximum: int) -> int:
    """Ask the user for an integer input within a specified range.

    :param prompt: The prompt to display to the user.
    :type prompt: str
    :param default: The default value if the user provides no input.
    :type default: int
    :param minimum: The minimum acceptable value.
    :type minimum: int
    :param maximum: The maximum acceptable value.
    :type maximum: int

    :return: The user's input as an integer.
    :rtype: int
    """
    while True:
        value = input(f"{prompt} [{default}]: ").strip() or str(default)
        try:
            number = int(value)
        except ValueError:
            print("Enter a whole number.")
            continue
        if minimum <= number <= maximum:
            return number
        print(f"Enter a value between {minimum} and {maximum}.")


def ask_secret(prompt: str) -> str:
    """Ask the user for a secret input (e.g., password) and confirm it.

    :param prompt: The prompt to display to the user.
    :type prompt: str

    :return: The user's input as a string.
    :rtype: str
    """
    while True:
        value = getpass.getpass(f"{prompt}: ")
        confirmation = getpass.getpass("Confirm: ")
        if not value:
            print("The secret cannot be empty.")
        elif value != confirmation:
            print("The values do not match.")
        else:
            return value


def ask_networks(prompt: str) -> list[str]:
    """Ask the user for a list of network CIDRs.

    :param prompt: The prompt to display to the user.
    :type prompt: str

    :return: A list of network CIDRs as strings.
    :rtype: list[str]
    """
    while True:
        values = input(f"{prompt} (comma-separated CIDRs): ").strip()
        try:
            networks = [
                str(ipaddress.ip_network(item.strip(), strict=False))
                for item in values.split(",")
                if item.strip()
            ]
        except ValueError:
            print("Each network must be a valid IPv4 or IPv6 CIDR.")
            continue
        if networks:
            return networks
        print("Enter at least one network.")


def ask_profile_durations() -> tuple[str, str]:
    """Ask the user for default and maximum profile durations.

    :return: A tuple containing the default and maximum durations as strings.
    :rtype: tuple[str, str]
    """
    while True:
        default_duration = ask_text("Default lease duration", "8h")
        maximum_duration = ask_text("Maximum lease duration", "24h")
        try:
            if parse_duration(default_duration) > parse_duration(maximum_duration):
                raise ValueError
        except (ValueError, TypeError):
            print(
                "Durations must use d, h, m, or s units, and the default cannot exceed the "
                "maximum."
            )
            continue
        return default_duration, maximum_duration


def ask_wireguard_interfaces() -> list[dict[str, Any]]:
    """Ask the user for WireGuard interface configurations.

    :return: A list of dictionaries containing interface configurations.
    :rtype: list[dict[str, Any]]
    """
    print_section(
        "WireGuard interfaces",
        "Each interface maps to a WireGuard device. Use its actual name and allowed "
        "client networks.",
    )
    count = ask_int("Number of WireGuard interfaces", 1, 1, 64)
    interfaces: list[dict[str, Any]] = []
    for index in range(count):
        print(f"WireGuard interface {index + 1}/{count}")
        name = ask_text("Interface name", f"wg{index}")
        description = ask_text("Profile description", name)
        networks = ask_networks("Allowed client networks")
        public_key = ask_text(
            "WireGuard interface public key (replace the placeholder if unknown)",
            WIREGUARD_PUBLIC_KEY_PLACEHOLDER,
        )
        default_duration, maximum_duration = ask_profile_durations()
        interfaces.append({
            "name": name,
            "description": description,
            "networks": networks,
            "public_key": public_key,
            "default_duration": default_duration,
            "maximum_duration": maximum_duration,
        })
    return interfaces


def ask_openvpn_profiles() -> tuple[str, list[dict[str, Any]]]:
    """Ask the user for OpenVPN profile configurations.

    :return: A tuple containing the server configuration path and a list of profile dictionaries.
    :rtype: tuple[str, list[dict[str, Any]]]
    """
    print_section(
        "OpenVPN draft profiles",
        "OpenVPN is not supported by the current application backend. These values are "
        "documentation only.",
    )
    server_config = ask_text(
        "OpenVPN server configuration path on the VPN host",
        "/etc/openvpn/server/server.conf",
    )
    count = ask_int("Number of OpenVPN profiles to document", 1, 1, 64)
    profiles: list[dict[str, Any]] = []
    for index in range(count):
        print(f"OpenVPN profile {index + 1}/{count}")
        name = ask_text("Profile name", f"profile-{index + 1}")
        description = ask_text("Description", name)
        networks = ask_networks("Allowed client networks")
        default_duration, maximum_duration = ask_profile_durations()
        profiles.append({
            "name": name,
            "description": description,
            "networks": networks,
            "default_duration": default_duration,
            "maximum_duration": maximum_duration,
        })
    return server_config, profiles


def _collect_authentication() -> tuple[dict[str, Any], bool]:
    print_section(
        "Authentication",
        "Choose a local administrator account or connect to an existing OpenID Connect provider.",
    )
    auth_mode = ask_choice("Authentication mode", ["internal", "external"], "internal")
    if auth_mode == "internal":
        return {
            "mode": "internal",
            "admin": {
                "username": ask_text("Initial administrator username", "admin"),
                "password": ask_secret("Initial administrator password"),
            },
        }, False
    return {
        "mode": "external",
        "admin": {"username": ask_text("Administrator username", "admin")},
        "oidc": {
            "issuer": ask_text("OIDC issuer URL"),
            "client_id": ask_text("OIDC client ID"),
            "redirect_uri": ask_text(
                "OIDC callback URL",
                "https://ttl-lama.example.org/auth/callback",
            ),
        },
        "success_redirect": ask_text(
            "Post-login redirect URL",
            "https://ttl-lama.example.org/",
        ),
    }, True


def _collect_database() -> tuple[dict[str, Any], bool]:
    print_section(
        "Database",
        "SQLite is suitable for a single application instance. Use a managed database for "
        "shared or high-availability deployments.",
    )
    database_type = ask_choice(
        "Database type",
        ["sqlite", "postgresql", "mysql", "mariadb"],
        "sqlite",
    )
    if database_type == "sqlite":
        return {
            "type": "sqlite",
            "path": ask_text("SQLite file path inside the container", "/data/ttl-lama.db"),
            "schema": "public",
        }, False
    default_port = 5432 if database_type == "postgresql" else 3306
    return {
        "type": database_type,
        "host": ask_text("Database host"),
        "port": ask_int("Database port", default_port, 1, 65535),
        "name": ask_text("Database name", "ttl_lama"),
        "schema": ask_text("Database schema", "public"),
        "user": ask_text("Database user"),
    }, True


def _collect_application() -> dict[str, Any]:
    print_section(
        "Application",
        "Choose the runtime environment. Debug mode should only be enabled for local development.",
    )
    environment = ask_choice("Environment", ["development", "production"], "production")
    debug = ask_bool("Enable debug mode", False) if environment == "development" else False
    return {
        "environment": environment,
        "debug": debug,
        "log_level": ask_choice(
            "Log level",
            ["debug", "info", "warning", "error"],
            "info",
        ),
        "server_port": ask_int("Listening port inside the container", 8080, 1, 65535),
        "published_port": ask_int("Port published on the host", 8080, 1, 65535),
    }


def _collect_security(environment: str) -> dict[str, Any]:
    print_section(
        "Security",
        "Argon2id suggestions are estimates, not benchmark results. Enter the CPU and memory "
        "limits available to this application container. The suggestion targets one quarter of "
        "memory, with an 8 MiB floor and a 256 MiB cap.",
    )
    cpu_default = max(1, min(64, os.cpu_count() or 1))
    cpu_cores = ask_int("CPU cores available to TTL-LAMa", cpu_default, 1, 64)
    memory_mib = ask_int("Memory available to TTL-LAMa (MiB)", 1024, 16, 1048576)
    suggested_parallelism = min(cpu_cores, 4)
    suggested_memory = min(262144, max(8192, memory_mib * 1024 // 4))
    suggested_hasher = {
        "time_cost": 3,
        "memory_cost": suggested_memory,
        "parallelism": suggested_parallelism,
        "hash_len": 32,
        "salt_len": 16,
    }
    print(
        "Suggested Argon2id settings: "
        f"time_cost={suggested_hasher['time_cost']}, "
        f"memory_cost={suggested_hasher['memory_cost']} KiB, "
        f"parallelism={suggested_hasher['parallelism']}, "
        f"hash_len={suggested_hasher['hash_len']}, "
        f"salt_len={suggested_hasher['salt_len']}."
    )
    use_suggestion = ask_bool("Use these suggested Argon2id settings?", True)
    if use_suggestion:
        password_hasher = suggested_hasher
    else:
        password_hasher = {
            "time_cost": ask_int("Argon2id time cost", 3, 1, 20),
            "memory_cost": ask_int("Argon2id memory cost (KiB)", 65536, 8192, 1048576),
            "parallelism": ask_int("Argon2id parallelism", 4, 1, 64),
            "hash_len": ask_int("Argon2id hash length", 32, 16, 128),
            "salt_len": ask_int("Argon2id salt length", 16, 8, 128),
        }
    enforce_secure = ask_bool("Require HTTPS", environment == "production")
    insecure_production_confirmed = False
    if environment == "production" and not enforce_secure:
        print(
            "WARNING: The application requires HTTPS in production and will reject this "
            "configuration at startup."
        )
        insecure_production_confirmed = ask_bool(
            "Generate the configuration anyway, knowing the application will not start?",
            False,
        )
        if not insecure_production_confirmed:
            raise ValueError("Configuration generation cancelled.")
    same_site_choices = ["Lax", "Strict"]
    if enforce_secure:
        same_site_choices.append("None")
    origins_text = input("Allowed origins, comma-separated [none]: ").strip()
    return {
        "password_hasher": password_hasher,
        "enforce_secure": enforce_secure,
        "insecure_production_confirmed": insecure_production_confirmed,
        "samesite": ask_choice("Cookie SameSite setting", same_site_choices, "Lax"),
        "session_lifetime": ask_int("Session lifetime in seconds", 3600, 60, 31536000),
        "allowed_origins": [item.strip() for item in origins_text.split(",") if item.strip()],
    }


def _collect_backend() -> tuple[str, dict[str, Any]]:
    print_section(
        "VPN backend",
        "WireGuard is supported. OpenVPN settings are generated as a non-executable draft only.",
    )
    backend_type = ask_choice("VPN backend", ["wireguard", "openvpn"], "wireguard")
    if backend_type == "wireguard":
        backend_settings = {"backend": {"wireguard": {"interfaces": ask_wireguard_interfaces()}}}
    else:
        server_config, profiles = ask_openvpn_profiles()
        backend_settings = {
            "backend": {"openvpn": {"server_config": server_config, "profiles": profiles}},
        }
    return backend_type, backend_settings


def _collect_ssh(vpn_host: str) -> dict[str, Any]:
    print_section(
        "SSH access to the VPN host",
        "Use a dedicated restricted account. The generated known_hosts file must be populated "
        "with the verified host key before startup.",
    )
    ssh_user = ask_text("Dedicated SSH username", "ttlama")
    if not re.fullmatch(r"[a-z_][a-z0-9_-]*[$]?", ssh_user):
        raise ValueError("The SSH username contains unsupported characters.")
    ssh_port = ask_int("SSH port", 22, 1, 65535)
    cli_path = ask_text("Absolute CLI path on the VPN host", DEFAULT_CLI_PATH)
    if not re.fullmatch(r"/[A-Za-z0-9_./-]+", cli_path):
        raise ValueError("The remote CLI path must be absolute and contain no spaces.")
    key_mode = ask_choice("SSH key", ["generate", "existing"], "generate")
    key_path: Path | None = None
    if key_mode == "existing":
        key_path = Path(ask_text("Path to the existing SSH private key")).expanduser().resolve()
        if not key_path.is_file():
            raise ValueError("The specified private key does not exist.")
    return {
        "vpn_host": vpn_host,
        "ssh_user": ssh_user,
        "ssh_port": ssh_port,
        "connection_timeout": ask_int("SSH connection timeout in seconds", 10, 1, 300),
        "cli_path": cli_path,
        "key_mode": key_mode,
        "key_path": key_path,
    }


def collect_answers() -> dict[str, Any]:
    """Collect and validate installation answers.

    :returns: The collected configuration values.
    :rtype: dict[str, Any]
    """
    print("TTL-LAMa installation configuration")
    print_section(
        "Network",
        "Enter the VPN host address as reachable from inside the application container.",
    )
    same_host = ask_bool("Are the application and VPN on the same machine?", True)
    vpn_host = ask_text(
        "VPN host reachable from the container",
        "host.containers.internal" if same_host else None,
    )
    authentication, oidc_secret = _collect_authentication()
    database, database_secret = _collect_database()
    application = _collect_application()
    security = _collect_security(application["environment"])
    backend_type, backend_settings = _collect_backend()
    ssh_settings = _collect_ssh(vpn_host)
    return {
        "same_host": same_host,
        "vpn_host": vpn_host,
        "auth": authentication,
        "oidc_secret": oidc_secret,
        "database": database,
        "database_secret": database_secret,
        **application,
        **security,
        "backend_type": backend_type,
        "backend_settings": backend_settings,
        **ssh_settings,
    }


def application_configuration(answers: dict[str, Any]) -> dict[str, Any]:
    """Generate the application configuration based on collected answers.

    :param answers: The collected installation answers.
    :type answers: dict[str, Any]

    :returns: The application configuration.
    :rtype: dict[str, Any]
    """
    auth = copy.deepcopy(answers["auth"])
    if auth["mode"] == "external":
        auth["oidc"]["client_secret"] = ""
    return {
        "app": {
            "environment": answers["environment"],
            "debug": answers["debug"],
            "secret_key_file": f"{CONTAINER_SECRETS}/flask_secret_key",
            "log_level": answers["log_level"],
        },
        "server": {"host": "0.0.0.0", "port": answers["server_port"]},
        "auth": {
            **auth,
            "cookie_name": "ttl-lama_session",
            "allowed_origins": answers["allowed_origins"],
            "password_hasher": answers["password_hasher"],
        },
        "database": answers["database"],
        "security": {
            "enforce_secure_connection": answers["enforce_secure"],
            "session_cookie_name": "session",
            "session_cookie_httponly": True,
            "session_cookie_secure": answers["enforce_secure"],
            "session_cookie_samesite": answers["samesite"],
            "session_cookie_path": "/",
            "session_lifetime": answers["session_lifetime"],
        },
        "backend_config": {"file": CONTAINER_BACKEND_CONFIG},
    }


def validate_application(
    configuration: dict[str, Any],
    allow_insecure_production: bool = False,
) -> None:
    """Validate the application configuration.

    :param configuration: The application configuration to validate.
    :type configuration: dict[str, Any]
    :param allow_insecure_production: Whether the user explicitly accepted the known production
    HTTPS startup rejection.
    :type allow_insecure_production: bool

    :raises ValueError: If the configuration is invalid.
    """
    candidate = copy.deepcopy(configuration)
    candidate["app"].pop("secret_key_file", None)
    candidate["app"]["secret_key"] = secrets.token_urlsafe(32)
    if candidate["auth"]["mode"] == "external":
        candidate["auth"]["oidc"]["client_secret"] = "validation-only-secret"
    if candidate["database"]["type"] != "sqlite":
        candidate["database"]["password"] = "validation-only-secret"
    if (
        allow_insecure_production
        and candidate["app"]["environment"] == "production"
        and not candidate["security"]["enforce_secure_connection"]
    ):
        candidate["security"]["enforce_secure_connection"] = True
        candidate["security"]["session_cookie_secure"] = True
    errors = validate_configuration(candidate)
    if errors:
        raise ValueError(
            "Invalid application configuration. Review the entered values and try again."
        )


def validate_backend(settings: dict[str, Any], backend_type: str) -> None:
    """Validate the backend configuration.

    :param settings: The backend settings to validate.
    :type settings: dict[str, Any]
    :param backend_type: The type of backend to validate.
    :type backend_type: str

    :raises ValueError: If the backend configuration is invalid.
    """
    if backend_type == "wireguard":
        BackendConfig.model_validate(settings)
        return
    openvpn = settings.get("backend", {}).get("openvpn", {})
    if not Path(openvpn.get("server_config", "")).is_absolute():
        raise ValueError("The OpenVPN configuration path must be absolute.")
    if not openvpn.get("profiles"):
        raise ValueError("At least one OpenVPN profile must be documented.")
    for profile in openvpn["profiles"]:
        default = parse_duration(profile["default_duration"])
        maximum = parse_duration(profile["maximum_duration"])
        if default > maximum:
            raise ValueError("The default OpenVPN duration cannot exceed the maximum duration.")


def validate_ssh(answers: dict[str, Any]) -> None:
    """Validate the SSH configuration.

    :param answers: The answers containing SSH configuration.
    :type answers: dict[str, Any]

    :raises ValueError: If the SSH configuration is invalid.
    """
    try:
        SSHConfiguration.model_validate({
            "host": answers["vpn_host"],
            "port": answers["ssh_port"],
            "user": answers["ssh_user"],
            "identity_file": f"{CONTAINER_SECRETS}/ttlama_ssh_key",
            "known_hosts_file": CONTAINER_KNOWN_HOSTS,
            "connection_timeout": answers["connection_timeout"],
        })
    except ValueError as error:
        raise ValueError(
            "Invalid SSH configuration. Review the entered values and try again."
        ) from error


def create_ssh_key(answers: dict[str, Any], secrets_dir: Path) -> str:
    """Create or import an SSH key.

    :param answers: The answers containing SSH key configuration.
    :type answers: dict[str, Any]
    :param secrets_dir: The directory to store the SSH key.
    :type secrets_dir: Path

    :return: The public key.
    :rtype: str

    :raises ValueError: If the SSH key configuration is invalid.
    """
    key_path = secrets_dir / "ttlama_ssh_key"
    ssh_keygen = shutil.which("ssh-keygen")
    if ssh_keygen is None:
        raise ValueError("ssh-keygen is required to manage the SSH key.")
    if answers["key_mode"] == "generate":
        subprocess.run(
            [ssh_keygen, "-q", "-t", "ed25519", "-N", "", "-f", str(key_path)],
            check=True,
            capture_output=True,
            text=True,
        )
        public_key = key_path.with_suffix(".pub").read_text(encoding="utf-8")
    else:
        source = answers["key_path"]
        if not isinstance(source, Path):
            raise ValueError("Invalid private key path.")
        public_key_result = subprocess.run(
            [ssh_keygen, "-y", "-f", str(source)],
            check=False,
            capture_output=True,
            text=True,
            input="",
        )
        if public_key_result.returncode != 0:
            raise ValueError("The SSH key must be unencrypted for BatchMode.")
        shutil.copyfile(source, key_path)
        public_key = public_key_result.stdout
        key_path.with_suffix(".pub").write_text(public_key + "\n", encoding="utf-8")
    public_key = public_key.strip()
    if not public_key.startswith("ssh-ed25519 "):
        raise ValueError("The identity key must be a dedicated Ed25519 key.")
    key_path.chmod(0o600)
    key_path.with_suffix(".pub").chmod(0o644)
    return public_key


def write_text(path: Path, content: str, mode: int = 0o644) -> None:
    """Write text to a file and set its permissions.

    :param path: The path to the file.
    :type path: Path
    :param content: The content to write.
    :type content: str
    :param mode: The file permissions mode.
    :type mode: int
    """
    path.write_text(content, encoding="utf-8")
    path.chmod(mode)


def write_yaml(path: Path, content: dict[str, Any], mode: int = 0o644) -> None:
    """Write YAML content to a file and set its permissions.

    :param path: The path to the file.
    :type path: Path
    :param content: The YAML content to write.
    :type content: dict[str, Any]
    :param mode: The file permissions mode.
    :type mode: int
    """
    write_text(path, yaml.safe_dump(content, sort_keys=False, allow_unicode=True), mode)


def sudoers_content(cli_path: str, remote_user: str) -> str:
    """Generate the sudoers content for the given CLI path and remote user.

    :param cli_path: The path to the CLI executable.
    :type cli_path: str
    :param remote_user: The remote user for sudoers configuration.
    :type remote_user: str

    :return: The sudoers content as a string.
    :rtype: str
    """
    return (
        f"Cmnd_Alias TTLAMA_WG_APPLY = {cli_path} backend wg leases apply --lease -\n"
        f"Cmnd_Alias TTLAMA_WG_DELETE = {cli_path} backend wg leases delete --lease -\n"
        f"{remote_user} ALL=(root) NOPASSWD: TTLAMA_WG_APPLY, TTLAMA_WG_DELETE\n"
    )


def render_wireguard_artifacts(
    staging_dir: Path,
    answers: dict[str, Any],
    public_key: str,
) -> None:
    """Render the WireGuard artifacts for the given staging directory and answers.

    :param staging_dir: The directory where the artifacts will be written.
    :type staging_dir: Path
    :param answers: The answers dictionary containing configuration values.
    :type answers: dict[str, Any]
    :param public_key: The public key to be used in the artifacts.
    :type public_key: str
    """
    template_dir = Path(__file__).parent / "templates"
    wrapper = (template_dir / "wireguard-ssh-wrapper.sh").read_text(encoding="utf-8")
    wrapper = wrapper.replace("@@CLI_PATH@@", shlex.quote(answers["cli_path"]))
    write_text(staging_dir / "ttlama-ssh-wrapper", wrapper, 0o755)
    write_text(
        staging_dir / "ttlama.sudoers",
        sudoers_content(answers["cli_path"], answers["ssh_user"]),
        0o440,
    )
    public_key_line = f'command="{WRAPPER_PATH}",restrict {public_key}'
    setup = (template_dir / "vpn-host-setup.sh").read_text(encoding="utf-8")
    setup = setup.replace("@@REMOTE_USER@@", shlex.quote(answers["ssh_user"]))
    setup = setup.replace("@@CLI_PATH@@", shlex.quote(answers["cli_path"]))
    setup = setup.replace("@@AUTHORIZED_KEY_LINE@@", shlex.quote(public_key_line))
    write_text(staging_dir / VPN_HOST_SETUP_FILE, setup, 0o755)
    write_text(staging_dir / "wireguard-ssh-key.pub", public_key + "\n")


def render_openvpn_artifacts(staging_dir: Path) -> None:
    """Render the OpenVPN artifacts for the given staging directory.

    :param staging_dir: The directory where the artifacts will be written.
    :type staging_dir: Path
    """
    template_dir = Path(__file__).parent / "templates"
    setup = (template_dir / "vpn-host-setup-openvpn.sh").read_text(encoding="utf-8")
    write_text(staging_dir / VPN_HOST_SETUP_FILE, setup, 0o755)
    write_text(
        staging_dir / "OPENVPN-NON-EXECUTABLE.txt",
        (template_dir / "OPENVPN-NON-EXECUTABLE.txt").read_text(encoding="utf-8"),
    )


def environment_template(answers: dict[str, Any]) -> str:
    """Render the environment template for the given answers.

    :param answers: The answers dictionary containing configuration values.
    :type answers: dict[str, Any]
    :return: The rendered environment template as a string.
    :rtype: str
    """
    variables = ["# Complete the required variables, then provide this file with --env-file."]
    if answers["oidc_secret"]:
        variables.append("TTL_LAMA_OIDC_CLIENT_SECRET=")
    if answers["database_secret"]:
        variables.append("TTL_LAMA_DB_PASSWORD=")
    return "\n".join(variables) + "\n"


def output_files(
    answers: dict[str, Any],
    configuration: dict[str, Any],
    output_dir: Path,
) -> Path:
    """Generate the output files for the given answers and configuration.

    :param answers: The answers dictionary containing configuration values.
    :type answers: dict[str, Any]
    :param configuration: The configuration dictionary containing application settings.
    :type configuration: dict[str, Any]
    :param output_dir: The directory where the output files will be written.
    :type output_dir: Path
    :return: The directory containing the generated installation files.
    :rtype: Path
    """
    output_dir = _unique_output_directory(output_dir)
    output_dir.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(
        prefix=f".{output_dir.name}-",
        dir=output_dir.parent,
    ) as temp_name:
        staging_dir = Path(temp_name) / "installation"
        staging_dir.mkdir(mode=0o700)
        etc_dir = staging_dir / "etc"
        etc_dir.mkdir(mode=0o700)
        config_dir = etc_dir / "ttl-lama"
        config_dir.mkdir(mode=0o700)
        run_dir = staging_dir / "run"
        run_dir.mkdir(mode=0o700)
        secret_dir = run_dir / "secrets"
        secret_dir.mkdir(mode=0o700)
        opt_dir = staging_dir / "opt"
        opt_dir.mkdir(mode=0o700)
        vpn_dir = opt_dir / "ttl-lama-vpn"
        vpn_dir.mkdir(mode=0o700)
        write_text(
            config_dir / "ssh_known_hosts",
            "# Add the verified VPN host key before starting TTL-LAMa.\n"
            "# Obtain the key from a trusted source and verify its fingerprint independently.\n",
            0o600,
        )
        write_text(secret_dir / "flask_secret_key", secrets.token_urlsafe(48) + "\n", 0o600)
        public_key = create_ssh_key(answers, secret_dir)
        write_yaml(config_dir / "config.yml", configuration, 0o600)
        write_yaml(config_dir / "backend_config.yml", answers["backend_settings"], 0o600)
        write_yaml(config_dir / "ssh_config.yml", {
            "ssh_config": {
                "host": answers["vpn_host"],
                "port": answers["ssh_port"],
                "user": answers["ssh_user"],
                "identity_file": f"{CONTAINER_SECRETS}/ttlama_ssh_key",
                "known_hosts_file": CONTAINER_KNOWN_HOSTS,
                "connection_timeout": answers["connection_timeout"],
            },
        }, 0o600)
        write_text(staging_dir / ".env.example", environment_template(answers))
        if answers["backend_type"] == "wireguard":
            render_wireguard_artifacts(vpn_dir, answers, public_key)
        else:
            render_openvpn_artifacts(vpn_dir)
        template_dir = Path(__file__).parent / "templates"
        write_text(
            staging_dir / "README.txt",
            (template_dir / "README.txt").read_text(encoding="utf-8"),
        )
        while True:
            try:
                output_dir.mkdir(mode=0o700)
            except FileExistsError:
                output_dir = _unique_output_directory(output_dir)
                continue
            try:
                staging_dir.rename(output_dir)
            except OSError:
                try:
                    output_dir.rmdir()
                except OSError:
                    pass
                raise
            return output_dir


def podman_commands(
    output_dir: Path,
    configuration: dict[str, Any],
    image: str,
    container_name: str,
    published_port: int,
) -> str:
    """Generate Podman commands for running the container.

    :param output_dir: The output directory containing configuration files.
    :type output_dir: Path
    :param configuration: The installation configuration dictionary.
    :type configuration: dict[str, Any]
    :param image: The container image to use.
    :type image: str
    :param container_name: The name of the container.
    :type container_name: str
    :param published_port: The port to publish on the host.
    :type published_port: int
    :returns: The generated Podman commands as a string.
    :rtype: str
    """
    server_port = configuration["server"]["port"]
    volume_name = f"{container_name}-data"
    if any(character in str(output_dir) for character in ":,\n"):
        raise ValueError("The output path cannot contain a colon, comma, or newline.")
    commands = [
        "podman volume create " + shlex.quote(volume_name),
        "podman run -d \\",
        "  --name " + shlex.quote(container_name) + " \\",
        "  --env-file " + shlex.quote(str(output_dir / ".env")) + " \\",
        "  -p " + shlex.quote(f"{published_port}:{server_port}") + " \\",
        VOLUME_MOUNT_PREFIX + shlex.quote(
            f"{output_dir / INSTALL_CONFIG_PATH / 'config.yml'}:{CONTAINER_CONFIG}:z,rw"
        ) + " \\",
        VOLUME_MOUNT_PREFIX + shlex.quote(
            f"{output_dir / INSTALL_CONFIG_PATH / 'backend_config.yml'}:"
            f"{CONTAINER_BACKEND_CONFIG}:z,ro"
        ) + " \\",
        VOLUME_MOUNT_PREFIX + shlex.quote(
            f"{output_dir / INSTALL_CONFIG_PATH / 'ssh_config.yml'}:{CONTAINER_SSH_CONFIG}:z,ro"
        ) + " \\",
        VOLUME_MOUNT_PREFIX + shlex.quote(
            f"{output_dir / INSTALL_CONFIG_PATH / 'ssh_known_hosts'}:{CONTAINER_KNOWN_HOSTS}:z,ro"
        ) + " \\",
        VOLUME_MOUNT_PREFIX + shlex.quote(
            f"{output_dir / INSTALL_SECRETS_PATH}:{CONTAINER_SECRETS}:z,ro"
        ) + " \\",
        VOLUME_MOUNT_PREFIX + shlex.quote(
            f"{volume_name}:/data:z,rw"
        ) + " \\",
        "  " + shlex.quote(image),
    ]
    return "\n".join(commands)


def parse_arguments() -> argparse.Namespace:
    """Parse command-line arguments for the installation script.

    :returns: The parsed arguments namespace.
    :rtype: argparse.Namespace
    """
    parser = argparse.ArgumentParser(description="Generate TTL-LAMa installation configuration.")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("ttl-lama-install"),
        help="Private output directory (default: ./ttl-lama-install).",
    )
    parser.add_argument("--image", default="ttl-lama:latest", help="Previously built image.")
    parser.add_argument("--container-name", default="ttl-lama")
    return parser.parse_args()


def main() -> int:
    """Collect, validate, and write installation configuration.

    :returns: The process exit code.
    :rtype: int
    """
    arguments = parse_arguments()
    output_dir = arguments.output_dir.expanduser().absolute()
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", arguments.container_name):
        print("Invalid container name.", file=sys.stderr)
        return 2
    if not arguments.image or any(character.isspace() for character in arguments.image):
        print("Invalid image name.", file=sys.stderr)
        return 2
    try:
        requested_output_dir = output_dir
        output_dir = _unique_output_directory(output_dir)
        if output_dir != requested_output_dir:
            print(f"Output directory already exists; using a unique path: {output_dir}")
        answers = collect_answers()
        configuration = application_configuration(answers)
        validate_application(
            configuration,
            allow_insecure_production=answers["insecure_production_confirmed"],
        )
        validate_backend(answers["backend_settings"], answers["backend_type"])
        validate_ssh(answers)
        generated_output_dir = output_files(answers, configuration, output_dir)
        if generated_output_dir != output_dir:
            print(
                f"Output directory became unavailable; using a unique path: "
                f"{generated_output_dir}"
            )
        output_dir = generated_output_dir
    except (OSError, ValueError, subprocess.SubprocessError, yaml.YAMLError) as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1
    print("\nConfiguration generated in:", output_dir)
    print("YAML preview (secrets redacted):")
    print(yaml.safe_dump(redact_secrets(configuration), sort_keys=False, allow_unicode=True))
    print("\nBefore startup:")
    print(
        f"  cp {shlex.quote(str(output_dir / '.env.example'))} "
        f"{shlex.quote(str(output_dir / '.env'))}"
    )
    print("  Complete the required variables in .env.")
    if answers["insecure_production_confirmed"]:
        print(
            "  WARNING: The application will reject this production configuration at startup "
            "because HTTPS is disabled."
        )
    print(
        f"  Add the verified VPN host key to "
        f"{output_dir / INSTALL_CONFIG_PATH / 'ssh_known_hosts'} before startup."
    )
    if answers["backend_type"] == "wireguard":
        print(
            "  Review, then manually run "
            f"{output_dir / INSTALL_VPN_PATH / VPN_HOST_SETUP_FILE} on the VPN host."
        )
        print("\nReview and run these Podman commands manually (they are not executed here):")
        print(podman_commands(
            output_dir,
            configuration,
            arguments.image,
            arguments.container_name,
            answers["published_port"],
        ))
    else:
        print(
            "\nOpenVPN is an unsupported draft; no podman run command is generated."
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
