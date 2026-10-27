"""Test cases for CSRF protection in the API v1."""

from flask import Flask
import pytest

from api.v1 import protect_cookie_authenticated_requests


class FakeCSRF: # pylint: disable=R0903
    """Fake CSRF class for testing purposes."""
    def __init__(self) -> None:
        self.protect_calls: list[bool] = []

    def protect(self, apply_exemptions: bool = True) -> None:
        """Simulate CSRF protection call."""
        self.protect_calls.append(apply_exemptions)


@pytest.mark.parametrize(
    "method",
    ("GET", "HEAD", "OPTIONS", "TRACE")
)
def test_safe_methods_skip_csrf(method: str) -> None:
    """Test that safe HTTP methods skip CSRF protection."""
    app = Flask(__name__)
    csrf = FakeCSRF()
    app.extensions["csrf"] = csrf

    with app.test_request_context("/api/v1/resource", method=method):
        protect_cookie_authenticated_requests()

    assert not csrf.protect_calls


def test_bearer_request_skips_csrf() -> None:
    """Test that requests with a Bearer token skip CSRF protection."""
    app = Flask(__name__)
    csrf = FakeCSRF()
    app.extensions["csrf"] = csrf

    with app.test_request_context(
        "/api/v1/resource",
        method="POST",
        headers={"Authorization": "Bearer cli-token"},
    ):
        protect_cookie_authenticated_requests()

    assert not csrf.protect_calls


def test_cookie_request_forces_csrf_validation() -> None:
    """Test that requests with cookies enforce CSRF validation."""
    app = Flask(__name__)
    csrf = FakeCSRF()
    app.extensions["csrf"] = csrf

    with app.test_request_context("/api/v1/resource", method="POST"):
        protect_cookie_authenticated_requests()

    assert csrf.protect_calls == [False]

def test_cookie_mutation_requires_csrf_token(csrf_app: Flask) -> None:
    """Test that cookie-based mutation requests require a CSRF token."""
    client = csrf_app.test_client()

    response = client.post("/test/mutate")

    assert response.status_code == 400

def test_cookie_mutation_accepts_valid_csrf_token(csrf_app: Flask) -> None:
    """Test that cookie-based mutation requests with a valid CSRF token are accepted."""
    client = csrf_app.test_client()
    token_response = client.get("/api/v1/csrf")

    assert token_response.status_code == 200
    assert token_response is not None

    token_data = token_response.get_json()
    assert isinstance(token_data, dict)

    csrf_token = token_data.get("csrf_token", None)   # type: ignore
    assert isinstance(csrf_token, str)

    response = client.post(
        "/test/mutate",
        headers={"X-CSRFToken": csrf_token}
    )

    assert response.status_code == 204

def test_bearer_mutation_skips_csrf_validation(csrf_app: Flask) -> None:
    """Test that mutation requests with a Bearer token skip CSRF validation."""
    client = csrf_app.test_client()

    response = client.post(
        "/test/mutate",
        headers={"Authorization": "Bearer cli-token"}
    )

    assert response.status_code == 204
