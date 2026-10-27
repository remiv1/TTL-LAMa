"""Tests for authentication routes."""

from typing import cast

import pytest
from flask import Response
from flask import Flask

from auth.backends import OIDCAuthBackend
from auth.manager import AuthManager


def test_login_starts_oidc_flow(
        oidc_app: Flask,
        monkeypatch: pytest.MonkeyPatch
) -> None:
    """Test that the login route initiates the OIDC flow."""
    def authorize_redirect(redirect_uri: str) -> Response:
        """Mock authorize_redirect to capture the redirect URI."""
        redirect_uris.append(redirect_uri)
        return Response(
            status=302,
            headers={"Location": "https://dex.example/authorize"}
        )
    manager = cast(AuthManager, oidc_app.extensions["auth_manager"])
    backend = cast(OIDCAuthBackend, manager.backend)
    redirect_uris: list[str] = []

    monkeypatch.setattr(
        backend.oidc_client,
        "authorize_redirect",
        authorize_redirect,
    )

    response = oidc_app.test_client().get("/auth/login")

    assert response.status_code == 302
    assert response.headers["Location"] == "https://dex.example/authorize"
    assert redirect_uris == [oidc_app.config["OIDC_REDIRECT_URI"]]
