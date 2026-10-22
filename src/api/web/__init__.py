"""API web package.

.. module_author:: Rémi Verschuur <rverschuur@audit-io.fr>
.. version:: 1.0.0
"""
from __future__ import annotations

from flask import Blueprint

web = Blueprint("web", __name__)
