"""Expose the API application factory.

.. module_author:: Rémi Verschuur <rverschuur@audit-io.fr>
.. version:: 1.0.0
"""
from api.bootstrap import create_app

__all__ = ["create_app"]
