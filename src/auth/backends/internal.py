"""Internal authentication backend for handling user authentication within the system.

.. module_author:: Rémi Verschuur <rverschuur@audit-io.fr>
.. version:: 1.0.0
"""
from __future__ import annotations
from typing import Literal, cast

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError

from api.common.other_objects import AuthMethod
from auth.backends.base import AuthBackend
from auth.models import UnifiedUser
from auth.services import UserService


class InternalAuthBackend(AuthBackend):
    """Authentification internal backend with username and password.
    
    :param user_service: The user service used for interacting with user data.
    :type user_service: UserService
    :param password_hasher: The configured Argon2id hasher.
    :type password_hasher: PasswordHasher
    
    ..author:: Rémi Verschuur <rverschuur@audit-io.fr>
    ..version:: 1.0.0
    """

    def __init__(
        self,
        user_service: UserService,
        password_hasher: PasswordHasher,
    ) -> None:
        self.user_service = user_service
        self.password_hasher = password_hasher

    def _validate_credentials(
        self,
        credentials: dict[str, object] | None,
    ) -> tuple[Literal[True], str, str] | tuple[Literal[False], None, None]:
        if credentials is None:
            return False, None, None
        username = credentials.get("username")
        password = credentials.get("password")
        if (
            not isinstance(username, str)
            or not username.strip()
            or not isinstance(password, str)
            or not password
        ):
            return False, None, None
        return True, username, password

    def authenticate(
        self,
        credentials: dict[str, object] | None = None,
    ) -> UnifiedUser | None:
        """Authenticate a user using internal credentials.

        :param credentials: A dictionary containing the username and password.
        :type credentials: dict[str, object] | None

        :return: The authenticated `UnifiedUser` object if authentication is successful,
        or None otherwise.
        :rtype: UnifiedUser | None
        """
        valid, username, password = self._validate_credentials(credentials)
        if not valid:
            return None

        user = self.user_service.get_by_username(cast(str, username))
        if user is None or not user.enabled:
            return None

        internal_credentials = [
            credential
            for credential in user.credentials
            if credential.auth_method == AuthMethod.INTERNAL.value
        ]
        if len(internal_credentials) != 1:
            return None

        try:
            self.password_hasher.verify(
                internal_credentials[0].hash_password,
                cast(str, password),
            )
        except (VerificationError, InvalidHashError):
            return None

        return UnifiedUser.from_db_user(user)

    def complete_login(self) -> UnifiedUser:
        """Complete the login process for internal authentication.

        Since internal authentication is handled synchronously, this method
        does not perform any additional actions.
        """
        raise NotImplementedError("Internal authentication does not require completing login.")
