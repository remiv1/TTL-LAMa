"""Local administrative commands for controlled account provisioning.

.. functions::
    - ``bootstrap_oidc_admin``: Create or link the configured initial OIDC administrator.
    - ``main``: Parse and run a local administrative command.

.. module_author:: Rémi Verschuur <rverschuur@audit-io.fr>
.. version:: 1.0.0
"""
from __future__ import annotations

import argparse
import sys

from api.config import DatabaseConfig, DatabaseSettings, FlaskSettings
from api.common.repositories import ConflictError
from auth.services.user import UserService


def bootstrap_oidc_admin(subject: str) -> tuple[str, bool, bool]:
    """Create or link the configured initial administrator to an OIDC identity.

    :param subject: The OIDC ``sub`` value, supplied as the Dex user ID.
    :type subject: str
    :return: The username, administrator flag, and enabled flag after provisioning.
    :rtype: tuple[str, bool, bool]
    :raises ValueError: If external authentication is not configured.
    :raises ConflictError: If the OIDC identity belongs to another account.
    """
    flask_settings = FlaskSettings()
    if flask_settings.AUTH_MODE != "external":
        raise ValueError("The local OIDC admin bootstrap requires external authentication")
    if not subject.strip():
        raise ValueError("The Dex user ID must not be empty")

    database = DatabaseConfig(DatabaseSettings())
    try:
        database.initialize()
        user = UserService(database.session()).create_initial_oidc_admin(
            username=flask_settings.ADMIN_USERNAME,
            issuer=flask_settings.OIDC_ISSUER.rstrip("/"),
            subject=subject,
        )
        return user.username, user.is_admin, user.enabled
    finally:
        database.close()


def main(argv: list[str] | None = None) -> int:
    """Run the selected local administrative command.

    :param argv: Optional command-line arguments, excluding the program name.
    :type argv: list[str] | None
    :return: The process exit code.
    :rtype: int
    """
    parser = argparse.ArgumentParser(description="Local TTL-LAMa administration")
    subparsers = parser.add_subparsers(dest="command", required=True)
    bootstrap_parser = subparsers.add_parser(
        "bootstrap-oidc-admin",
        help="Create or link the configured administrator to a Dex user ID",
    )
    bootstrap_parser.add_argument(
        "--user-id",
        required=True,
        help="Dex userID value, used as the OIDC subject",
    )
    arguments = parser.parse_args(argv)

    try:
        username, is_admin, enabled = bootstrap_oidc_admin(arguments.user_id)
    except (ConflictError, ValueError) as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1

    print(f"OIDC identity linked to configured account {username!r}.")
    if not is_admin or not enabled:
        print(
            "Warning: the existing account's administrator and enabled state were preserved.",
            file=sys.stderr,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
