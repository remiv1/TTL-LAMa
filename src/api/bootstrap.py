"""Assemble the Flask application and its extensions.

.. functions::
    - `create_app`: Create the Flask application and initialize its extensions.

.. module_author:: Rémi Verschuur <rverschuur@audit-io.fr>
.. version:: 1.0.0
"""
from __future__ import annotations

import logging

from flask import Flask, Response, jsonify
from flask_wtf.csrf import CSRFProtect
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from api.config import AccessProfiles, DatabaseConfig, DatabaseSettings, FlaskSettings
from auth.manager import AuthManager
from auth.routes import auth_bp

LOGGER = logging.getLogger(__name__)


def create_app(
    flask_settings: FlaskSettings | None = None,
    database_settings: DatabaseSettings | None = None,
) -> Flask:
    """Create the application, initialize its database, and register its routes.

    :param flask_settings: Optional Flask and authentication settings.
    :type flask_settings: FlaskSettings | None
    :param database_settings: Optional persistence settings.
    :type database_settings: DatabaseSettings | None
    :returns: The Flask application ready to serve requests.
    :rtype: Flask

    """
    flask_settings = flask_settings or FlaskSettings()
    database_settings = database_settings or DatabaseSettings()

    app = Flask(__name__)
    app.config.update(
        DEBUG=flask_settings.DEBUG,
        SECRET_KEY=flask_settings.SECRET_KEY,
        SESSION_COOKIE_NAME=flask_settings.SESSION_COOKIE_NAME,
        SESSION_COOKIE_HTTPONLY=flask_settings.SESSION_COOKIE_HTTPONLY,
        SESSION_COOKIE_SECURE=flask_settings.SESSION_COOKIE_SECURE,
        SESSION_COOKIE_SAMESITE=flask_settings.SESSION_COOKIE_SAMESITE,
        SESSION_COOKIE_PATH=flask_settings.SESSION_COOKIE_PATH,
        MAX_CONTENT_LENGTH=flask_settings.MAX_CONTENT_LENGTH,
        WTF_CSRF_ENABLED=True,
        WTF_CSRF_CHECK_DEFAULT=True,
        TESTING=flask_settings.FLASK_ENV.lower() == "testing",
    )

    profiles = AccessProfiles.from_file(flask_settings.ACCESS_PROFILES_FILE)
    database = DatabaseConfig(database_settings)
    database.initialize()
    AuthManager.initialize_database(database.session, flask_settings)
    auth_manager = AuthManager(app, database.session, flask_settings)
    app.extensions["database_config"] = database
    app.extensions["auth_manager"] = auth_manager
    app.config["ACCESS_PROFILES"] = profiles.profiles

    CSRFProtect(app)
    app.register_blueprint(auth_bp)

    @app.get("/health")
    def health() -> tuple[Response, int]:
        """Return service readiness based on database connectivity.

        :returns: A JSON response and the corresponding HTTP status.
        :rtype: tuple[Response, int]
        """
        try:
            with database.engine.connect() as connection:
                connection.execute(text("SELECT 1"))
        except SQLAlchemyError:
            LOGGER.exception("Database health check failed")
            return jsonify(status="unavailable"), 503
        return jsonify(status="ok"), 200

    @app.after_request
    def set_security_headers(response: Response) -> Response:
        """Add security headers to every outgoing response.

        :param response: The response being sent to the client.
        :type response: Response
        :returns: The response with security headers applied.
        :rtype: Response
        """
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Content-Security-Policy"] = (
            "default-src 'none'; frame-ancestors 'none'; base-uri 'none'"
        )
        if flask_settings.ENFORCE_SECURE_CONNECTION:
            response.headers["Strict-Transport-Security"] = "max-age=31536000"
        return response

    @app.teardown_appcontext
    def remove_database_session(_error: BaseException | None) -> None:
        """Remove the scoped database session at the end of the request.

        :param _error: An exception raised during request handling, if any.
        :type _error: BaseException | None
        :returns: ``None``.
        :rtype: None
        """
        database.session.remove()

    return app
