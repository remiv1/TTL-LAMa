"""Tests for the web interface and its session workflows."""

from typing import cast

from flask import Flask
from flask.testing import FlaskClient


def _csrf_headers(client: FlaskClient) -> dict[str, str]:
    response = client.get("/api/v1/csrf")
    payload = cast(dict[str, object], response.get_json())
    token = payload.get("csrf_token")
    assert isinstance(token, str)
    return {"X-CSRFToken": token}


def test_homepage_defaults_to_english_and_uses_local_assets(app: Flask) -> None:
    """Test that the homepage defaults to English and uses local assets."""
    client = app.test_client()

    response = client.get("/")
    body = response.get_data(as_text=True)

    assert response.status_code == 200
    assert response.mimetype == "text/html"
    assert '<html lang="en">' in body
    assert "Temporary access. Automatic revocation." in body
    assert "/web/static/css/main.css" in body
    assert "/web/static/js/htmx.min.js" in body
    assert 'name="htmx-config"' in body
    assert "includeIndicatorStyles" in body
    assert "<script>" not in body
    assert " style=" not in body

    stylesheet = client.get("/web/static/css/main.css")
    htmx = client.get("/web/static/js/htmx.min.js")
    assert stylesheet.status_code == 200
    assert htmx.status_code == 200

    fragment = client.get("/devices", headers={"HX-Request": "true"})
    fragment_body = fragment.get_data(as_text=True)
    assert fragment.status_code == 200
    assert 'id="main-content"' not in fragment_body
    assert "<header" not in fragment_body
    assert "<footer" not in fragment_body
    assert "not available yet" in fragment_body


def test_language_choice_is_saved_and_untrusted_redirect_is_rejected(
    app: Flask,
) -> None:
    """Test that the language choice is saved and untrusted redirects are rejected."""
    client = app.test_client()
    response = client.post(
        "/language",
        data={"language": "fr", "next": "//example.invalid"},
        headers=_csrf_headers(client),
    )

    assert response.status_code == 303
    assert response.headers["Location"] == "/"
    backslash_response = client.post(
        "/language",
        data={"language": "fr", "next": "/\\example.invalid"},
        headers=_csrf_headers(client),
    )
    assert backslash_response.headers["Location"] == "/"
    homepage = client.get("/").get_data(as_text=True)
    assert '<html lang="fr">' in homepage
    assert "Accès temporaire. Révocation automatique." in homepage


def test_navigation_is_keyboard_operable_and_sections_are_explicitly_pending(
    app: Flask,
) -> None:
    """Test that the navigation is keyboard operable and sections are explicitly pending."""
    client = app.test_client()
    homepage = client.get("/").get_data(as_text=True)

    assert 'type="button" data-menu-toggle' in homepage
    assert 'aria-controls="main-menu" aria-expanded="false"' in homepage
    assert 'id="main-menu"' in homepage

    for path in ("/devices", "/leases", "/profiles"):
        response = client.get(path)
        assert response.status_code == 200
        assert "not available yet" in response.get_data(as_text=True)


def test_internal_login_account_status_and_logout(app: Flask) -> None:
    """Test the internal login, account status, and logout functionality."""
    client = app.test_client()
    username = cast(str, app.config["TEST_ADMIN_USERNAME"])

    login_page = client.get("/login")
    assert login_page.status_code == 200
    assert 'name="csrf_token"' in login_page.get_data(as_text=True)

    login = client.post(
        "/auth/login",
        data={
            "username": username,
            "password": "correct-horse-battery",
        },
        headers=_csrf_headers(client),
    )
    assert login.status_code == 303
    assert login.headers["Location"] == "/"

    account = client.get("/account")
    assert account.status_code == 200
    assert username in account.get_data(as_text=True)
    assert "Your session is active." in account.get_data(as_text=True)

    logout = client.post("/logout", headers=_csrf_headers(client))
    assert logout.status_code == 303
    assert logout.headers["Location"] == "/"
    assert any(
        value.startswith(f"{app.config['AUTH_COOKIE_NAME']}=")
        and "Max-Age=0" in value
        for value in logout.headers.getlist("Set-Cookie")
    )
    assert client.get("/account").status_code == 302


def test_security_policy_allows_only_local_ui_resources(app: Flask) -> None:
    """Test that the security policy allows only local UI resources."""
    response = app.test_client().get("/")
    policy = response.headers["Content-Security-Policy"]

    assert "script-src 'self'" in policy
    assert "style-src 'self'" in policy
    assert "connect-src 'self'" in policy
    assert "unsafe-inline" not in policy
