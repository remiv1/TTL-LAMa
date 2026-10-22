"""API version 1 package.

.. module_author:: Rémi Verschuur <rverschuur@audit-io.fr>
.. version:: 1.0.0
"""
from __future__ import annotations

from flask import Blueprint

api_v1 = Blueprint("api_v1", __name__, url_prefix="/api/v1")
