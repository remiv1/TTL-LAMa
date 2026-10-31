"""Assemble the Flask application and its extensions.

.. functions::
    - `create_app`: Create the Flask application and initialize its extensions.
    - `get_sessions`: Return a new database scoped_session.

.. constants::
    - `LOGGER`: Logger instance for the module.

.. module_author:: Rémi Verschuur <rverschuur@audit-io.fr>
.. version:: 1.0.0
"""
from __future__ import annotations

import logging
from typing import Any, Protocol, cast
from datetime import timedelta

from argon2 import PasswordHasher
from authlib.integrations.flask_client import OAuth
from authlib.integrations.flask_client.apps import FlaskOAuth2App
from flask import Flask, Response, current_app
from flask_wtf.csrf import CSRFProtect
from flask_cors import CORS
from sqlalchemy.orm import Session

from api.config import (
    AccessProfiles,
    DatabaseConfig,
    DatabaseSettings,
    FlaskSettings,
    PasswordHasherSettings,
)
from api.v1 import api_v1
from api.v1.admin import admin
from api.v1.user import user_api
from api.common.repositories import ProfileRepository
from api.web import web
from auth import (
    auth_bp,
    OIDCAuthBackend,
    InternalAuthBackend,
    AuthManager,
    SessionService,
    UserService,
    OIDCParams,
)

LOGGER = logging.getLogger(__name__)


class _OAuthRegistry(Protocol): # pylint: disable=R0903
    """Protocol for OAuth registry objects.

    This protocol defines the interface for objects that can register OAuth clients.
    
    .. author:: Rémi Verschuur <rverschuur@audit-io.fr>
    .. version:: 1.0.0
    """
    def register(self, name: str, overwrite: bool = False, **kwargs: Any) -> FlaskOAuth2App:
        """Register an OAuth client. This types the OAuth client registration who has bad
        type hints.

        :param name: The name of the OAuth client.
        :type name: str
        :param overwrite: Whether to overwrite an existing client with the same name.
        :type overwrite: bool
        :param kwargs: Additional keyword arguments for the OAuth client registration.
        :type kwargs: Any
        :returns: The registered OAuth client.
        :rtype: FlaskOAuth2App
        """
        ... # pylint: disable=W2301


def _configure_cors(app: Flask, settings: FlaskSettings) -> None:
    """Configure authorized CORS origins.
    
    :param app: The Flask application instance.
    :type app: Flask
    :param settings: The Flask settings containing CORS configuration.
    :type settings: FlaskSettings
    """
    if not settings.CORS_ALLOWED_ORIGINS:
        return
    CORS(
        app,
        resources={
            r"/api/v1/*": {
                "origins": settings.CORS_ALLOWED_ORIGINS,
                "supports_credentials": True,
                "methods": ["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
                "allow_headers": [
                    "Content-Type",
                    "Authorization",
                    "X-CSRFToken",
                    "X-CSRF-Token",
                ],
            },
        },
    )


def _register_oidc_client(app: Flask, settings: FlaskSettings) -> None:
    """Register the OIDC client in the Flask application.

    :param app: The Flask application instance.
    :type app: Flask
    :param settings: The Flask settings containing OIDC configuration.
    :type settings: FlaskSettings
    """
    oauth = cast(_OAuthRegistry, OAuth(app))
    issuer = settings.OIDC_ISSUER.rstrip("/")
    app.extensions["oidc_client"] = oauth.register(
        name="oidc",
        server_metadata_url=f"{issuer}/.well-known/openid-configuration",
        client_id=settings.OIDC_CLIENT_ID,
        client_secret=settings.OIDC_CLIENT_SECRET,
        client_kwargs={"scope": "openid"},
    )


def _create_auth_manager(
    app: Flask,
    database: DatabaseConfig,
    flask_settings: FlaskSettings,
    password_hasher_settings: PasswordHasherSettings | None,
) -> AuthManager:
    """Constructs the session services and the authentication backend for the Flask app
    depending on the authentication mode specified in the Flask settings.

    :param app: The Flask application instance.
    :type app: Flask
    :param database: The database configuration.
    :type database: DatabaseConfig
    :param flask_settings: The Flask settings containing authentication configuration.
    :type flask_settings: FlaskSettings
    :param password_hasher_settings: The settings for the password hasher, if any.
    :type password_hasher_settings: PasswordHasherSettings | None
    :returns: The constructed authentication manager.
    :rtype: AuthManager
    """
    db_session = cast(Session, database.session)
    user_service = UserService(db_session)
    session_service = SessionService(
        db_session,
        timedelta(seconds=flask_settings.SESSION_LIFETIME),
    )
    if flask_settings.AUTH_MODE == "external":
        backend = OIDCAuthBackend(
            user_service,
            OIDCParams(
                oidc_client=cast(
                    FlaskOAuth2App,
                    app.extensions["oidc_client"],
                ),
                issuer=flask_settings.OIDC_ISSUER.rstrip("/"),
                redirect_uri=flask_settings.OIDC_REDIRECT_URI,
            ),
        )
    else:
        settings = password_hasher_settings or PasswordHasherSettings()
        password_hasher = PasswordHasher(
            time_cost=settings.TIME_COST,
            memory_cost=settings.MEMORY_COST,
            parallelism=settings.PARALLELISM,
            hash_len=settings.HASH_LEN,
            salt_len=settings.SALT_LEN,
        )
        if user_service.get_by_username(flask_settings.ADMIN_USERNAME) is None:
            user_service.create_initial_admin(
                username=flask_settings.ADMIN_USERNAME,
                password_hash=password_hasher.hash(flask_settings.ADMIN_PASSWORD),
            )
        backend = InternalAuthBackend(
            user_service,
            password_hasher,
        )
    return AuthManager(backend, session_service, user_service)


def _register_blueprints(app: Flask) -> None:
    """Register the blueprints and configure CSRF protection.

    :param app: The Flask application instance.
    :type app: Flask
    """
    csrf = CSRFProtect(app)
    # Exempt the API v1 blueprint from CSRF protection. These routes are protected
    # by other means, such as authentication and authorization mechanisms.
    csrf.exempt(api_v1) # NOSONAR
    csrf.exempt(admin) # NOSONAR - parent hook enforces CSRF for cookie requests
    csrf.exempt(user_api) # NOSONAR - parent hook enforces CSRF for cookie requests
    for blueprint in (auth_bp, api_v1, web):
        app.register_blueprint(blueprint)


def _register_security_headers(app: Flask, settings: FlaskSettings) -> None:
    """Add security headers to Flask responses.

    :param app: The Flask application instance.
    :type app: Flask
    :param settings: The Flask settings containing security configuration.
    :type settings: FlaskSettings
    """
    @app.after_request
    def set_security_headers(response: Response) -> Response:
        """Add security headers to every outgoing response."""
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Content-Security-Policy"] = (
            "default-src 'none'; script-src 'self'; style-src 'self'; "
            "img-src 'self' data:; font-src 'self'; connect-src 'self'; "
            "form-action 'self'; base-uri 'self'; object-src 'none'; "
            "frame-ancestors 'none'"
        )
        if settings.ENFORCE_SECURE_CONNECTION:
            response.headers["Strict-Transport-Security"] = "max-age=31536000"
        return response


def _register_database_teardown(app: Flask, database: DatabaseConfig) -> None:
    """Remove the SQLAlchemy session at the end of each application context.

    :param app: The Flask application instance.
    :type app: Flask
    :param database: The database configuration.
    :type database: DatabaseConfig
    """
    @app.teardown_appcontext
    def remove_database_session(_error: BaseException | None) -> None:
        """Remove the current database session at the end of the application context.
        
        :param _error: The error that occurred during the application context teardown, if any.
        :type _error: BaseException | None
        """
        database.session.remove()


def create_app(
    flask_settings: FlaskSettings | None = None,
    database_settings: DatabaseSettings | None = None,
    password_hasher_settings: PasswordHasherSettings | None = None,
) -> Flask:
    """Create the application, initialize its database, and register its routes.

    :param flask_settings: Optional Flask and authentication settings.
    :type flask_settings: FlaskSettings | None
    :param database_settings: Optional persistence settings.
    :type database_settings: DatabaseSettings | None
    :param password_hasher_settings: Optional Argon2id settings.
    :type password_hasher_settings: PasswordHasherSettings | None
    :returns: The Flask application ready to serve requests.
    :rtype: Flask
    """
    flask_settings = flask_settings or FlaskSettings()
    database_settings = database_settings or DatabaseSettings()
    app = Flask(__name__)
    app.config.from_mapping(flask_settings.model_dump())
    _configure_cors(app, flask_settings)
    if flask_settings.AUTH_MODE == "external":
        _register_oidc_client(app, flask_settings)

    profiles = AccessProfiles.from_file(flask_settings.ACCESS_PROFILES_FILE)
    database = DatabaseConfig(database_settings)
    database.initialize()
    with database.session().begin():
        ProfileRepository(database.session()).import_missing(profiles)
    app.extensions["auth_manager"] = _create_auth_manager(
        app,
        database,
        flask_settings,
        password_hasher_settings,
    )
    app.extensions["database_config"] = database
    app.config["ACCESS_PROFILES"] = profiles.profiles
    _register_blueprints(app)
    _register_security_headers(app, flask_settings)
    _register_database_teardown(app, database)
    return app


def get_sessions() -> Session:
    """Return a new database session.

    :returns: A SQLAlchemy session.
    :rtype: Session
    """
    return current_app.extensions["database_config"].session()
