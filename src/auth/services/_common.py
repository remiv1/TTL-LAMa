"""Common services for authentication.

.. classes::
    - `ServiceMixin`: Mixin class for common authentication services.

    
.. module_author:: Rémi Verschuur <rverschuur@audit-io.fr>
.. version:: 1.0
"""
from __future__ import annotations

from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError

class ServiceMixin:
    """Mixin class for common authentication services."""
    def __init__(self, session: Session):
        self.db_session = session

    def commit(self):
        """Commits the current transaction."""
        try:
            self.db_session.commit()
        except SQLAlchemyError as e:
            self.rollback()
            raise e

    def rollback(self):
        """Rolls back the current transaction."""
        self.db_session.rollback()
