"""HTTP controller for authentication endpoints."""

from __future__ import annotations

from typing import cast

from flask import Response, current_app, jsonify, redirect
from werkzeug import Response as WerkzeugResponse

from auth.manager import AuthManager
from auth.models import AuthenticationResult, UnifiedUser


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

    def begin_oidc_login(self) -> Response | tuple[Response, int]:
        """Initiate the OIDC login process."""
        try:
            response = self.auth_manager.begin_login()
        except RuntimeError:
            return jsonify(error="OIDC client not configured"), 501

        if response is None:
            return jsonify(error="OIDC client not configured"), 501

        return response

    def oidc_callback(self) -> WerkzeugResponse:
        """Handle the callback from the OIDC provider."""
        result = self.auth_manager.complete_login()
        app_config = cast(dict[str, object], current_app.config)
        target = cast(str, app_config.get("AUTH_SUCCESS_REDIRECT") or "/")

        response = redirect(target)
        self._set_auth_cookie(response, result.session_token)
        response.headers["Cache-Control"] = "no-store"
        return response
