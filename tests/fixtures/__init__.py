"""Fixtures package for TTL-LAMa tests."""

from __future__ import annotations

from ._common import login_admin
from .auth import oidc_settings
from .database import database_settings, app
from .users import user_with_oidc_identity, user_service

__all__ = [
    "login_admin",
    "oidc_settings",
    "user_with_oidc_identity",
    "user_service",
    "database_settings",
    "app",
]
