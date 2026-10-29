"""Persist validated access policies separately from historical profile records."""
from __future__ import annotations

from sqlalchemy import ForeignKey, JSON, String
from sqlalchemy.orm import Mapped, mapped_column

from ._common import Base, TABLE_ARGS, foreign_key_target


class ProfilePolicy(Base):
    """One current policy per profile; adding this table needs no column migration."""

    __tablename__ = "profile_policies"
    __table_args__ = TABLE_ARGS

    profile_id: Mapped[int] = mapped_column(
        ForeignKey(foreign_key_target("profiles")), primary_key=True
    )
    default_duration: Mapped[str] = mapped_column(String(255), nullable=False)
    maximum_duration: Mapped[str] = mapped_column(String(255), nullable=False)
    networks: Mapped[list[str]] = mapped_column(JSON, nullable=False)
