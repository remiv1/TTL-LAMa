"""Tests for OIDC integration."""

import pytest
import requests

from api.config import FlaskSettings


@pytest.mark.oidc
def test_dex_publishes_valid_discovery_document(
    oidc_settings: FlaskSettings,
) -> None:
    """Test that Dex publishes a valid OIDC discovery document."""
    issuer = oidc_settings.OIDC_ISSUER.rstrip("/")
    discovery_url = f"{issuer}/.well-known/openid-configuration"

    response = requests.get(discovery_url, timeout=5)
    response.raise_for_status()
    metadata = response.json()

    assert metadata["issuer"] == issuer
    assert metadata["code_challenge_methods_supported"] == ['S256', 'plain']
    assert "public" in metadata["subject_types_supported"]
    assert all(a in metadata["grant_types_supported"] for a in [
        'authorization_code',
        'client_credentials',
        'password',
        'refresh_token',
        'urn:ietf:params:oauth:grant-type:device_code',
    ])
    assert all(a in metadata["scopes_supported"] for a in [
        "openid",
        "groups",
        "profile",
    ])
    assert "authorization_endpoint" in metadata
    assert "token_endpoint" in metadata
    assert "jwks_uri" in metadata
    assert "userinfo_endpoint" in metadata
    assert "device_authorization_endpoint" in metadata
    assert "introspection_endpoint" in metadata
    assert "end_session_endpoint" in metadata
    assert "backchannel_logout_supported" in metadata
    assert "backchannel_logout_session_supported" in metadata
    assert "response_types_supported" in metadata
    assert "id_token_signing_alg_values_supported" in metadata
    assert "token_endpoint_auth_methods_supported" in metadata
    assert "claims_supported" in metadata
