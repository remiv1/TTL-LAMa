"""Shared persistence primitives; callers own the transaction.

.. classes::
    - `NotFoundError`: Raised when an entity is not found in the repository.
    - `ConflictError`: Raised when an operation conflicts with the current state.
    - `Repository`: Generic repository for managing domain objects.

.. module_author:: Rémi Verschuur <rverschuur@audit-io.fr>
.. version:: 1.0.0
"""
from __future__ import annotations

from typing import Generic, TypeVar

from sqlalchemy import select
from sqlalchemy.orm import Session
from sqlalchemy.sql.elements import ColumnElement

from api.common.db_objects._common import Base

Model = TypeVar("Model", bound=Base)


class NotFoundError(ValueError):
    """The requested domain object does not exist.
    
    .. from:: `ValueError`
    
    .. author:: Rémi Verschuur <rverschuur@audit-io.fr>
    .. version:: 1.0.0
    """


class ConflictError(ValueError):
    """The requested operation conflicts with the current state.

    .. from:: `ValueError`

    .. author:: Rémi Verschuur <rverschuur@audit-io.fr>
    .. version:: 1.0.0
    """


class Repository(Generic[Model]):
    """Read and stage changes without committing a caller's transaction.
    
    :param session: The SQLAlchemy session to use for database operations.
    :type session: Session
    :param model: The SQLAlchemy model class managed by this repository.
    :type model: type[Model]

    .. author:: Rémi Verschuur <rverschuur@audit-io.fr>
    .. version:: 1.0.0
    """

    def __init__(self, session: Session, model: type[Model]) -> None:
        self.session = session
        self.model = model

    def get(self, identifier: int | str, *, refresh: bool = False) -> Model:
        """Returns an object or raise an explicit not-found error.

        :param identifier: The primary key of the object to retrieve.
        :type identifier: int | str
        :param refresh: Whether to refresh the object from the database.
        :type refresh: bool
        :raises NotFoundError: If the object does not exist.
        :return: The retrieved object.
        :rtype: Model
        """
        instance = self.session.get(self.model, identifier, populate_existing=refresh)
        if instance is None:
            raise NotFoundError(f"{self.model.__name__} not found")
        return instance

    def list(self, *conditions: ColumnElement[bool]) -> list[Model]:
        """Return matching objects in primary-key order.
        
        :param conditions: The conditions to filter the objects.
        :type conditions: ColumnElement[bool]
        :return: The list of matching objects.
        :rtype: list[Model]
        """
        return list(self.session.scalars(
            select(self.model).where(*conditions).order_by(*self.model.__mapper__.primary_key)
        ).unique())

    def add(self, instance: Model) -> Model:
        """Stages a new object and populate generated identifiers.

        :param instance: The object to add to the session.
        :type instance: Model
        :return: The staged object with populated identifiers.
        :rtype: Model
        """
        self.session.add(instance)
        self.session.flush()
        return instance
