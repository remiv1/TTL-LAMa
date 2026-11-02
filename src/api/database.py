"""Access the current Flask request's SQLAlchemy session.

.. functions::
    - `get_session`: Return the session associated with the current scope.

.. module_author:: Rémi Verschuur <rverschuur@audit-io.fr>
.. version:: 1.0.0
"""
from __future__ import annotations

from flask import current_app
from sqlalchemy.orm import Session


def get_session() -> Session:
    """Return the SQLAlchemy session associated with the current scope.

    :returns: The session associated with the current Flask application context.
    :rtype: sqlalchemy.orm.Session
    """
    return current_app.extensions["database_config"].session()
