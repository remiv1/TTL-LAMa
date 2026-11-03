"""Tests for administrative global configuration endpoints."""
from __future__ import annotations

from pathlib import Path
from typing import cast

import pytest
import yaml
from flask import Flask
from flask.testing import FlaskClient
from werkzeug.test import TestResponse


def _valid_configuration() -> dict[str, object]:
    """Return a minimal valid configuration for the application settings models."""
    return {
        "app": {
            "environment": "testing",
            "debug": False,
            "secret_key": "test-secret-key-with-at-least-thirty-two-characters",
        },
        "server": {"host": "127.0.0.1", "port": 8080},
        "auth": {
            "mode": "internal",
            "admin": {"username": "admin", "password": "valid-password"},
        },
        "database": {"type": "sqlite", "path": ":memory:"},
        "security": {
            "enforce_secure_connection": False,
            "session_cookie_secure": False,
        },
    }


def _write_config(path: Path, configuration: dict[str, object]) -> None:
    path.write_text(yaml.safe_dump(configuration, sort_keys=False), encoding="utf-8")


def _admin_headers(domain: object) -> dict[str, str]:
    return cast(dict[str, str], getattr(domain, "headers"))


def test_get_global_config_redacts_direct_secrets(
    domain: object,
    app: Flask, # pylint: disable=W0613
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The read endpoint returns the YAML structure but never direct secrets."""
    config = _valid_configuration()
    config["database"] = {"type": "postgresql", "password": "database-secret"}
    config["auth"] = {
        "mode": "external",
        "admin": {"username": "admin", "password": "admin-secret"},
        "oidc": {"client_secret": "oidc-secret"},
    }
    cast(dict[str, object], config["app"])["secret_key"] = "flask-secret"
    config_path = tmp_path / "config.yml"
    _write_config(config_path, config)
    monkeypatch.setenv("TTL_LAMA_CONFIG_FILE", str(config_path))

    response = getattr(domain, "client").get(
        "/api/v1/global-config",
        headers=_admin_headers(domain),
    )

    assert response.status_code == 200
    route = next(
        rule for rule in app.url_map.iter_rules()
        if rule.rule == "/api/v1/global-config"
    )
    assert route.endpoint.startswith("api_v1.global_config.")
    assert response.headers["Cache-Control"] == "no-store"
    result = cast(dict[str, object], response.get_json())
    assert cast(dict[str, object], result["app"])["secret_key"] == "[REDACTED]"
    auth = cast(dict[str, object], result["auth"])
    assert cast(dict[str, object], auth["admin"])["password"] == "[REDACTED]"
    assert cast(dict[str, object], auth["oidc"])["client_secret"] == "[REDACTED]"
    assert cast(dict[str, object], result["database"])["password"] == "[REDACTED]"
    assert "flask-secret" not in response.get_data(as_text=True)


def test_validate_global_config_is_read_only_and_rejects_redacted_values(
    domain: object,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Validation does not persist the candidate and rejects masked secrets."""
    config_path = tmp_path / "config.yml"
    original = _valid_configuration()
    _write_config(config_path, original)
    original_contents = config_path.read_text(encoding="utf-8")
    monkeypatch.setenv("TTL_LAMA_CONFIG_FILE", str(config_path))
    client: FlaskClient = getattr(domain, "client")
    headers = _admin_headers(domain)

    invalid = _valid_configuration()
    cast(dict[str, object], invalid["app"])["secret_key"] = "[REDACTED]"
    invalid_response: TestResponse = client.post(
        "/api/v1/global-config/validate",
        headers=headers,
        json=invalid,
    )
    valid_response: TestResponse = client.post(
        "/api/v1/global-config/validate",
        headers=headers,
        json=_valid_configuration(),
    )

    assert invalid_response.status_code == 200
    assert invalid_response.get_json() == {
        "valid": False,
        "errors": ["Replace [REDACTED] with a value or a secret-file reference."],
    }
    assert valid_response.get_json() == {"valid": True, "errors": []}
    assert config_path.read_text(encoding="utf-8") == original_contents


def test_global_config_requires_administrator_authentication(app: Flask) -> None:
    """The independent blueprint rejects unauthenticated requests as admin does."""
    client = app.test_client()
    response = client.get("/api/v1/global-config")
    admin_response = client.get("/api/v1/admin/users")

    assert response.status_code == 401
    assert response.get_json() == admin_response.get_json()


def test_apply_global_config_persists_and_warns_without_a_volume(
    domain: object,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Apply writes the candidate and reports a non-persistent target."""
    import api.v1   # pylint: disable=C0415

    config_path = tmp_path / "config.yml"
    monkeypatch.setenv("TTL_LAMA_CONFIG_FILE", str(config_path))

    def no_volume_mount(_path: Path) -> bool:
        return False

    monkeypatch.setattr(api.v1, "is_volume_mounted", no_volume_mount)

    response = getattr(domain, "client").post(
        "/api/v1/global-config/apply",
        headers=_admin_headers(domain),
        json=_valid_configuration(),
    )

    assert response.status_code == 200
    result = cast(dict[str, object], response.get_json())
    assert result["applied"] is True
    assert result["restart_required"] is True
    assert isinstance(result["warning"], str)
    assert yaml.safe_load(config_path.read_text(encoding="utf-8")) == _valid_configuration()


def test_apply_global_config_rejects_redacted_candidate_without_writing(
    domain: object,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Apply rejects masked secrets and leaves the existing file unchanged."""
    config_path = tmp_path / "config.yml"
    original = _valid_configuration()
    _write_config(config_path, original)
    original_contents = config_path.read_text(encoding="utf-8")
    monkeypatch.setenv("TTL_LAMA_CONFIG_FILE", str(config_path))
    invalid = _valid_configuration()
    cast(dict[str, object], invalid["app"])["secret_key"] = "[REDACTED]"

    response = getattr(domain, "client").post(
        "/api/v1/global-config/apply",
        headers=_admin_headers(domain),
        json=invalid,
    )

    assert response.status_code == 400
    assert config_path.read_text(encoding="utf-8") == original_contents
