"""Tests for administrative global configuration endpoints."""
from __future__ import annotations

import logging
from pathlib import Path
from typing import cast

import pytest
import yaml
from flask import Flask
from flask.testing import FlaskClient
from pydantic import ValidationError
from werkzeug.test import TestResponse

from api.config import FlaskSettings


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


def test_compare_global_config_returns_only_unchanged_secret_paths(
    domain: object,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Comparison identifies equal secrets without returning their values."""
    config_path = tmp_path / "config.yml"
    current = _valid_configuration()
    _write_config(config_path, current)
    monkeypatch.setenv("TTL_LAMA_CONFIG_FILE", str(config_path))
    candidate = _valid_configuration()
    candidate_auth = cast(dict[str, object], candidate["auth"])
    candidate_admin = cast(dict[str, object], candidate_auth["admin"])
    candidate_admin["password"] = "changed-password"

    response = getattr(domain, "client").post(
        "/api/v1/global-config/compare",
        headers=_admin_headers(domain),
        json=candidate,
    )

    assert response.status_code == 200
    assert response.get_json() == {"unchanged_secrets": ["app.secret_key"]}
    response_text = response.get_data(as_text=True)
    assert "test-secret-key-with-at-least-thirty-two-characters" not in response_text
    assert "valid-password" not in response_text
    assert "changed-password" not in response_text


def test_compare_global_config_recognizes_matching_passwords(
    domain: object,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Equal direct passwords are reported by path only."""
    config_path = tmp_path / "config.yml"
    _write_config(config_path, _valid_configuration())
    monkeypatch.setenv("TTL_LAMA_CONFIG_FILE", str(config_path))

    response = getattr(domain, "client").post(
        "/api/v1/global-config/compare",
        headers=_admin_headers(domain),
        json=_valid_configuration(),
    )

    assert response.status_code == 200
    assert response.get_json() == {
        "unchanged_secrets": ["app.secret_key", "auth.admin.password"],
    }
    assert "valid-password" not in response.get_data(as_text=True)


def test_validate_global_config_does_not_mutate_resolved_file_secret(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Runtime file secrets do not become false direct values on revalidation."""
    from api.config.global_config import validate_configuration  # pylint: disable=C0415

    secret_file = tmp_path / "flask-secret"
    secret_file.write_text(
        "test-secret-key-with-at-least-thirty-two-characters",
        encoding="utf-8",
    )
    monkeypatch.setenv("TTL_LAMA_SECRET_KEY_FILE", str(secret_file))
    candidate = _valid_configuration()
    app_config = cast(dict[str, object], candidate["app"])
    app_config.pop("secret_key")
    app_config["secret_key_file"] = str(secret_file)

    assert not validate_configuration(candidate)


def test_validate_global_config_still_rejects_explicit_secret_and_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A candidate cannot configure both direct and file-based secret sources."""
    from api.config.global_config import validate_configuration  # pylint: disable=C0415

    monkeypatch.delenv("TTL_LAMA_SECRET_KEY_FILE", raising=False)
    secret_file = tmp_path / "flask-secret"
    secret_file.write_text(
        "test-secret-key-with-at-least-thirty-two-characters",
        encoding="utf-8",
    )
    candidate = _valid_configuration()
    cast(dict[str, object], candidate["app"])["secret_key_file"] = str(secret_file)

    errors = validate_configuration(candidate)

    assert any("Configurer SECRET_KEY ou son fichier, pas les deux" in error for error in errors)


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


def test_global_config_yaml_error_does_not_expose_contents(
    domain: object,
    caplog: pytest.LogCaptureFixture,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Malformed YAML errors stay generic in both the API response and log."""
    secret = "yaml-secret-sentinel"
    config_path = tmp_path / "malformed.yml"
    config_path.write_text(f"app: [{secret}", encoding="utf-8")
    monkeypatch.setenv("TTL_LAMA_CONFIG_FILE", str(config_path))
    caplog.set_level(logging.ERROR)

    response = getattr(domain, "client").get(
        "/api/v1/global-config",
        headers=_admin_headers(domain),
    )

    assert response.status_code == 500
    assert response.get_json() == {"error": "Unable to read the application configuration."}
    assert secret not in response.get_data(as_text=True)
    assert secret not in " ".join(record.getMessage() for record in caplog.records)


@pytest.mark.parametrize("secret_file_state", ["missing", "unreadable"])
def test_secret_file_errors_are_generic(
    secret_file_state: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Missing and unreadable authentication secret files produce generic errors."""
    secret_path = tmp_path / "auth-secret"
    secret = "authentication-secret-sentinel"
    if secret_file_state == "unreadable":
        secret_path.write_text(secret, encoding="utf-8")
        original_read_text = Path.read_text

        def deny_secret_read(
            path: Path,
            encoding: str | None = None,
            errors: str | None = None,
        ) -> str:
            if path == secret_path:
                raise PermissionError("simulated secret-file denial")
            return original_read_text(path, encoding=encoding, errors=errors)

        monkeypatch.setattr(Path, "read_text", deny_secret_read)
    monkeypatch.setenv("TTL_LAMA_CONFIG_FILE", str(tmp_path / "absent-config.yml"))
    monkeypatch.delenv("TTL_LAMA_SECRET_KEY", raising=False)

    with pytest.raises(ValidationError) as error:
        FlaskSettings(
            FLASK_ENV="testing",
            SECRET_KEY_FILE=secret_path,
            ENFORCE_SECURE_CONNECTION=False,
            SESSION_COOKIE_SECURE=False,
        )  # type: ignore[call-arg]

    assert "Impossible de lire le fichier secret SECRET_KEY" in str(error.value)
    assert secret not in str(error.value)
    assert str(secret_path) not in str(error.value)


def test_secret_file_override_conflict_does_not_expose_secret_values(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Environment file overrides cannot combine with a YAML direct secret."""
    direct_secret = "yaml-direct-secret-sentinel"
    file_secret = "file-secret-sentinel"
    configuration = _valid_configuration()
    cast(dict[str, object], configuration["app"])["secret_key"] = direct_secret
    config_path = tmp_path / "config.yml"
    _write_config(config_path, configuration)
    secret_path = tmp_path / "flask-secret"
    secret_path.write_text(file_secret, encoding="utf-8")
    monkeypatch.setenv("TTL_LAMA_CONFIG_FILE", str(config_path))
    monkeypatch.setenv("TTL_LAMA_SECRET_KEY_FILE", str(secret_path))
    monkeypatch.delenv("TTL_LAMA_SECRET_KEY", raising=False)

    with pytest.raises(ValidationError) as error:
        FlaskSettings()

    message = str(error.value)
    assert "Configurer SECRET_KEY ou son fichier, pas les deux" in message
    assert direct_secret not in message
    assert file_secret not in message
