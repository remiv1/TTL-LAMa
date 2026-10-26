"""Authentication-related exceptions.

.. author:: Rémi Verschuur <rverschuur@audit-io.fr>
.. version:: 1.0.0
"""

class AuthenticationError(Exception):
    """Exception raised for authentication-related errors."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message

class AccountNotFoundError(AuthenticationError):
    """Exception raised when a user is not registered."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message

class InvalidCredentialsError(AuthenticationError):
    """Exception raised when provided credentials are invalid."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message

class OIDCAuthenticationError(AuthenticationError):
    """Exception raised for OIDC authentication-related errors."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message
