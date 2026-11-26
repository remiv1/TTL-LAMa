"""Tests for administrative global configuration endpoints."""
from __future__ import annotations

import logging
import runpy
from pathlib import Path
from types import SimpleNamespace
from typing import cast
from unittest.mock import Mock

import pytest
import yaml
from flask import Flask
from flask.testing import FlaskClient
from pydantic import ValidationError
from werkzeug.test import TestResponse

from api.bootstrap import create_app
from api.config import DatabaseSettings, FlaskSettings


@pytest.mark.parametrize("include", [False, True])
def test_installer_proposes_external_firewall_without_executing_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, include: bool,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Generate recommendations and optional commented rules without running commands."""
    installer = runpy.run_path(
        str(Path(__file__).resolve().parents[2] / "scripts/install/configure.py")
    )
    settings = {"backend": {"wireguard": {"profiles": [{
        "name": "files", "interface": "wg0", "default_duration": "1h", "maximum_duration": "2h",
        "networks": ["10.20.0.0/24"], "address_pools": ["10.250.0.0/24"],
        "endpoint": "vpn.example.test:51820", "public_key": "server-key",
    }]}}}

    def forbidden(*args: object, **kwargs: object) -> None:
        raise AssertionError("Installer rendering must not execute a command")

    monkeypatch.setattr(installer["subprocess"], "run", forbidden)
    proposed = installer["nftables_recommendations"](settings)
    assert 'iifname "wg0" ip saddr 10.250.0.0/24 ip daddr { 10.20.0.0/24 } accept' in proposed
    assert "NOT per-profile authorization" in proposed
    installer["render_wireguard_artifacts"](tmp_path, {
        "cli_path": "/opt/ttlama/bin/ttlama", "ssh_user": "ttlama", "vpn_host": "vpn.example.test",
        "ssh_port": 22, "include_nftables": include, "backend_settings": settings,
    }, "ssh-ed25519 public-test-key")
    script = (tmp_path / "vpn-host-setup.sh").read_text(encoding="utf-8")
    assert ("# table inet ttl_lama_integration" in script) is include
    assert "nft -" not in script
    namespace = installer["main"].__globals__
    answers = {
        "backend_type": "wireguard", "backend_settings": settings,
        "insecure_production_confirmed": False, "published_port": 8080,
    }
    monkeypatch.setitem(namespace, "parse_arguments", lambda: SimpleNamespace(
        output_dir=tmp_path / "bundle", image="ttlama:test", container_name="ttlama-test",
    ))
    monkeypatch.setitem(namespace, "collect_answers", lambda: answers)
    monkeypatch.setitem(
        namespace, "application_configuration",
        Mock(return_value={"server": {"port": 8080}}),
    )
    monkeypatch.setitem(namespace, "validate_application", Mock(return_value=None))
    monkeypatch.setitem(namespace, "validate_ssh", Mock(return_value=None))
    monkeypatch.setitem(namespace, "output_files", Mock(return_value=tmp_path / "bundle"))
    assert installer["main"]() == 0
    stdout = capsys.readouterr().out
    assert proposed in stdout
    assert "router administrator responsibility" in stdout


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


@pytest.mark.parametrize("secure", [False, True])
def test_production_transport_sets_cookie_security(secure: bool) -> None:
    """Production supports both transports with matching cookie security."""
    configuration = _valid_configuration()
    cast(dict[str, object], configuration["app"])["environment"] = "production"
    configuration["security"] = {"enforce_secure_connection": secure}

    settings = FlaskSettings.model_validate(configuration)

    assert settings.SESSION_COOKIE_SECURE is secure
    assert settings.SESSION_COOKIE_HTTPONLY


@pytest.mark.parametrize("secure", [False, True])
def test_production_login_uses_transport_cookie_settings(tmp_path: Path, secure: bool) -> None:
    """A production login emits the expected cookie and transport headers."""
    configuration = _valid_configuration()
    cast(dict[str, object], configuration["app"])["environment"] = "production"
    configuration["security"] = {"enforce_secure_connection": secure}
    settings = FlaskSettings.model_validate(configuration)
    application = create_app(settings, DatabaseSettings(DB_PATH=str(tmp_path / "test.db")))
    try:
        client = application.test_client()
        base_url = "https://localhost" if secure else "http://localhost"
        csrf_response = client.get("/api/v1/csrf", base_url=base_url)
        token = cast(dict[str, str], csrf_response.get_json())["csrf_token"]
        response = client.post(
            "/auth/login",
            base_url=base_url,
            json={"username": "admin", "password": "valid-password"},
            headers={"X-CSRFToken": token, "Referer": f"{base_url}/login"},
        )

        assert response.status_code == 200
        cookie = client.get_cookie(settings.AUTH_COOKIE_NAME)
        assert cookie is not None
        assert cookie.secure is secure
        assert cookie.http_only
        assert ("Strict-Transport-Security" in response.headers) is secure
    finally:
        application.extensions["database_config"].close()


def test_production_http_keeps_cookie_and_debug_restrictions() -> None:
    """HTTP does not permit debug mode or insecure SameSite=None cookies."""
    configuration = _valid_configuration()
    app_config = cast(dict[str, object], configuration["app"])
    app_config["environment"] = "production"
    app_config["debug"] = True
    with pytest.raises(ValidationError, match="DEBUG"):
        FlaskSettings.model_validate(configuration)

    app_config["debug"] = False
    configuration["security"] = {
        "enforce_secure_connection": False,
        "session_cookie_samesite": "None",
    }
    with pytest.raises(ValidationError, match="SAMESITE"):
        FlaskSettings.model_validate(configuration)

    configuration["security"] = {
        "enforce_secure_connection": False,
        "session_cookie_secure": True,
    }
    with pytest.raises(ValidationError, match="SESSION_COOKIE_SECURE"):
        FlaskSettings.model_validate(configuration)


@pytest.mark.parametrize(
    "secure,issuer,redirect,valid",
    [
        (False, "https://identity.example.test", "http://app.example.test/auth/callback", True),
        (True, "https://identity.example.test", "https://app.example.test/auth/callback", True),
        (False, "http://identity.example.test", "http://app.example.test/auth/callback", False),
        (True, "https://identity.example.test", "http://app.example.test/auth/callback", False),
    ],
)
def test_production_oidc_transport_validation(
    secure: bool, issuer: str, redirect: str, valid: bool,
) -> None:
    """OIDC requires a secure issuer and a secure callback when HTTPS is enforced."""
    configuration = _valid_configuration()
    cast(dict[str, object], configuration["app"])["environment"] = "production"
    configuration["security"] = {"enforce_secure_connection": secure}
    configuration["auth"] = {
        "mode": "external",
        "oidc": {
            "issuer": issuer,
            "client_id": "client",
            "client_secret": "secret",
            "redirect_uri": redirect,
        },
    }
    if valid:
        FlaskSettings.model_validate(configuration)
    else:
        with pytest.raises(ValidationError):
            FlaskSettings.model_validate(configuration)


def test_installer_validates_actual_production_http_configuration() -> None:
    """The installer accepts HTTP but does not hide invalid cookie settings."""
    installer = runpy.run_path(
        str(Path(__file__).resolve().parents[2] / "scripts/install/configure.py")
    )
    configuration = _valid_configuration()
    cast(dict[str, object], configuration["app"])["environment"] = "production"
    installer["validate_application"](configuration)

    cast(dict[str, object], configuration["security"])["session_cookie_secure"] = True
    with pytest.raises(ValueError, match="Invalid application configuration"):
        installer["validate_application"](configuration)


@pytest.mark.parametrize("confirmed", [False, True])
def test_installer_confirms_production_http(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], confirmed: bool,
) -> None:
    """The installer warns and requires explicit confirmation for production HTTP."""
    installer = runpy.run_path(
        str(Path(__file__).resolve().parents[2] / "scripts/install/configure.py")
    )
    collect = installer["_collect_security"]
    namespace = collect.__globals__
    answers = iter([True, False, confirmed])

    def fake_ask_bool(_prompt: str, _default: bool) -> bool:
        return next(answers)

    def fake_ask_int(_prompt: str, default: int, _minimum: int, _maximum: int) -> int:
        return default

    def fake_ask_choice(_prompt: str, _choices: list[str], default: str) -> str:
        return default

    def fake_input(_prompt: str) -> str:
        return ""

    monkeypatch.setitem(namespace, "ask_bool", fake_ask_bool)
    monkeypatch.setitem(namespace, "ask_int", fake_ask_int)
    monkeypatch.setitem(namespace, "ask_choice", fake_ask_choice)
    monkeypatch.setattr("builtins.input", fake_input)

    if confirmed:
        result = collect("production")
        assert result["insecure_production_confirmed"]
        assert not result["enforce_secure"]
    else:
        with pytest.raises(ValueError, match="cancelled"):
            collect("production")
    assert "trusted, isolated network" in capsys.readouterr().out


def test_login_lock_settings_load_from_nested_yaml() -> None:
    """The login retry and lock-duration settings are read from the auth section."""
    configuration = _valid_configuration()
    auth = cast(dict[str, object], configuration["auth"])
    auth["max_connect_retry"] = 5
    auth["login_lock_duration_seconds"] = 600

    settings = FlaskSettings.model_validate(configuration)

    assert settings.MAX_CONNECT_RETRY == 5
    assert settings.LOGIN_LOCK_DURATION_SECONDS == 600


@pytest.mark.parametrize(
    "key,value",
    [
        ("max_connect_retry", 0),
        ("max_connect_retry", 101),
        ("login_lock_duration_seconds", 0),
        ("login_lock_duration_seconds", 86401),
    ],
)
def test_login_lock_settings_reject_out_of_range_values(
    key: str,
    value: int,
) -> None:
    """Retry and lock duration settings must remain within supported bounds."""
    configuration = _valid_configuration()
    cast(dict[str, object], configuration["auth"])[key] = value

    with pytest.raises(ValidationError):
        FlaskSettings.model_validate(configuration)


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
            FLASK_ENV="testing",    # type: ignore
            SECRET_KEY_FILE=secret_path,    # type: ignore
            ENFORCE_SECURE_CONNECTION=False,    # type: ignore
            SESSION_COOKIE_SECURE=False,    # type: ignore
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
