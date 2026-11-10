"""HTTP controller for authentication endpoints."""

from __future__ import annotations

import re
from typing import cast
from urllib.parse import urlencode, urlsplit, urlunsplit

from flask import Response, current_app, jsonify, redirect, session, url_for
from werkzeug import Response as WerkzeugResponse

from auth.manager import AuthManager
from auth.exceptions import OIDCAuthenticationError
from auth.models import AuthenticationResult, UnifiedUser
from auth.services.cli_login_ticket import (
    CLI_LOGIN_TICKET_LIFETIME,
    CliLoginTicketService,
)

_CLI_LOGIN_CONTEXT = "cli_oidc_login"
_CLI_STATE_PATTERN = re.compile(r"^[A-Za-z0-9_-]{32,128}$")


class AuthController:
    """Build HTTP responses for authentication requests."""

    def __init__(self, auth_manager: AuthManager) -> None:
        self.auth_manager = auth_manager

    def api_login(self, payload: object) -> Response | tuple[Response, int]:
        """Authenticate credentials and return a Bearer token."""
        result = self._authenticate(payload)
        if not isinstance(result, AuthenticationResult):
            return result

        response = jsonify(
            user=self._user_payload(result.user),
            access_token=result.session_token,
            token_type="Bearer",
        )
        response.headers["Cache-Control"] = "no-store"
        return response

    def gui_login(self, payload: object) -> Response | tuple[Response, int]:
        """Authenticate credentials and set the session cookie."""
        result = self._authenticate(payload)
        if not isinstance(result, AuthenticationResult):
            return result

        response = jsonify(user=self._user_payload(result.user))
        self._set_auth_cookie(response, result.session_token)
        response.headers["Cache-Control"] = "no-store"
        return response

    def _authenticate(
        self,
        payload: object,
    ) -> AuthenticationResult | tuple[Response, int]:
        """Validate the request and authenticate its credentials."""
        app_config = cast(dict[str, object], current_app.config)
        if app_config.get("AUTH_MODE") != "internal":
            return jsonify(error="Credential authentication is not enabled"), 405

        if not isinstance(payload, dict):
            return jsonify(error="A JSON object is required"), 400

        result = self.auth_manager.authenticate(cast(dict[str, object], payload))
        if result is None:
            return jsonify(error="Invalid username or password"), 401

        return result

    @staticmethod
    def _user_payload(user: UnifiedUser) -> dict[str, str | bool | None]:
        return {
            "id": user.id,
            "username": user.username,
            "email": user.email,
            "is_admin": user.is_admin,
        }

    @staticmethod
    def _set_auth_cookie(response: Response | WerkzeugResponse, token: str) -> None:
        """Set the configured HTTP-only authentication cookie."""
        app_config = cast(dict[str, object], current_app.config)
        response.set_cookie(
            key=cast(str, app_config["AUTH_COOKIE_NAME"]),
            value=token,
            max_age=cast(int, app_config["SESSION_LIFETIME"]),
            httponly=cast(bool, app_config["SESSION_COOKIE_HTTPONLY"]),
            secure=cast(bool, app_config["SESSION_COOKIE_SECURE"]),
            samesite=cast(str, app_config["SESSION_COOKIE_SAMESITE"]),
            path=cast(str, app_config["SESSION_COOKIE_PATH"]),
        )

    def begin_oidc_login(
        self,
        callback_url: str | None = None,
        cli_state: str | None = None,
    ) -> Response | tuple[Response, int]:
        """Initiate the OIDC login process."""
        if callback_url is not None or cli_state is not None:
            if not self._valid_cli_callback(callback_url, cli_state):
                return jsonify(error="Invalid CLI callback parameters"), 400
            session[_CLI_LOGIN_CONTEXT] = {
                "callback_url": callback_url,
                "state": cli_state,
            }

        try:
            response = self.auth_manager.begin_login()
        except RuntimeError:
            return jsonify(error="OIDC client not configured"), 501

        if response is None:
            return jsonify(error="OIDC client not configured"), 501

        return response

    def oidc_callback(self) -> WerkzeugResponse | tuple[WerkzeugResponse, int]:
        """Handle the callback from the OIDC provider."""
        cli_context = session.pop(_CLI_LOGIN_CONTEXT, None)
        if isinstance(cli_context, dict):
            context = cast(dict[str, object], cli_context)
            callback_url = context.get("callback_url")
            cli_state = context.get("state")
            if not self._valid_cli_callback(callback_url, cli_state):
                return jsonify(error="Invalid CLI login state"), 400

            try:
                user = self.auth_manager.backend.complete_login()
            except OIDCAuthenticationError:
                return self._oidc_failure_response(context)
            ticket_service = CliLoginTicketService(
                self.auth_manager.session_service.db_session,
                CLI_LOGIN_TICKET_LIFETIME,
            )
            ticket = ticket_service.create(user.id)
            callback_parts = urlsplit(cast(str, callback_url))
            callback_query = urlencode(
                {"ticket": ticket, "state": cast(str, cli_state)},
            )
            response = redirect(
                urlunsplit(
                    (
                        callback_parts.scheme,
                        callback_parts.netloc,
                        callback_parts.path,
                        callback_query,
                        "",
                    )
                )
            )
            response.headers["Cache-Control"] = "no-store"
            return response

        try:
            result = self.auth_manager.complete_login()
        except OIDCAuthenticationError:
            return self._oidc_failure_response(None)
        app_config = cast(dict[str, object], current_app.config)
        target = cast(str, app_config.get("AUTH_SUCCESS_REDIRECT") or "/")

        response = redirect(target)
        self._set_auth_cookie(response, result.session_token)
        response.headers["Cache-Control"] = "no-store"
        return response

    def oidc_error_callback(
        self,
        provider_state: object,
    ) -> WerkzeugResponse | tuple[WerkzeugResponse, int]:
        """Return provider denial to a waiting CLI without exposing provider details."""
        cli_context = session.pop(_CLI_LOGIN_CONTEXT, None)
        self.auth_manager.backend.validate_error_state(provider_state)
        return self._oidc_failure_response(cli_context)

    @staticmethod
    def _oidc_failure_response(
        cli_context: object,
    ) -> WerkzeugResponse | tuple[WerkzeugResponse, int]:
        """Return a generic, non-authenticating response for an OIDC failure."""
        if not isinstance(cli_context, dict):
            response = redirect(url_for("web.login", error="oidc"))
            response.headers["Cache-Control"] = "no-store"
            return response

        context = cast(dict[str, object], cli_context)
        callback_url = context.get("callback_url")
        cli_state = context.get("state")
        if not AuthController._valid_cli_callback(callback_url, cli_state):
            return jsonify(error="Invalid CLI login state"), 400

        callback_parts = urlsplit(cast(str, callback_url))
        response = redirect(
            urlunsplit(
                (
                    callback_parts.scheme,
                    callback_parts.netloc,
                    callback_parts.path,
                    urlencode({"state": cli_state, "error": "access_denied"}),
                    "",
                )
            )
        )
        response.headers["Cache-Control"] = "no-store"
        return response

    @staticmethod
    def _valid_cli_callback(callback_url: object, cli_state: object) -> bool:
        """Accept only the CLI's loopback callback and a high-entropy state value."""
        if not isinstance(callback_url, str) or not isinstance(cli_state, str):
            return False
        if not _CLI_STATE_PATTERN.fullmatch(cli_state):
            return False
        try:
            parsed = urlsplit(callback_url)
            port = parsed.port
        except ValueError:
            return False
        return (
            parsed.scheme == "http"
            and parsed.hostname == "127.0.0.1"
            and port is not None
            and 1 <= port <= 65535
            and parsed.path == "/callback"
            and not parsed.username
            and not parsed.password
            and not parsed.query
            and not parsed.fragment
        )
