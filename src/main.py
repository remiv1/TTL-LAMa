"""Expose the TTL-LAMa WSGI application.

.. module_author:: Rémi Verschuur <rverschuur@audit-io.fr>
.. version:: 1.0.0
"""
from api.bootstrap import create_app

app = create_app()
