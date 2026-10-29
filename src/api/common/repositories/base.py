"""Shared persistence primitives; callers own the transaction."""
from __future__ import annotations

from typing import Generic, TypeVar

from sqlalchemy import select
from sqlalchemy.orm import Session
from sqlalchemy.sql.elements import ColumnElement

from api.common.db_objects._common import Base

Model = TypeVar("Model", bound=Base)


class NotFoundError(ValueError):
    """The requested domain object does not exist."""


class ConflictError(ValueError):
    """The requested operation conflicts with the current state."""


class Repository(Generic[Model]):
    """Read and stage changes without committing a caller's transaction."""

    def __init__(self, session: Session, model: type[Model]) -> None:
        self.session = session
        self.model = model

    def get(self, identifier: int | str, *, refresh: bool = False) -> Model:
        """Return an object or raise an explicit not-found error."""
        instance = self.session.get(self.model, identifier, populate_existing=refresh)
        if instance is None:
            raise NotFoundError(f"{self.model.__name__} not found")
        return instance

    def list(self, *conditions: ColumnElement[bool]) -> list[Model]:
        """Return matching objects in primary-key order."""
        return list(self.session.scalars(
            select(self.model).where(*conditions).order_by(*self.model.__mapper__.primary_key)
        ).unique())

    def add(self, instance: Model) -> Model:
        """Stage a new object and populate generated identifiers."""
        self.session.add(instance)
        self.session.flush()
        return instance
