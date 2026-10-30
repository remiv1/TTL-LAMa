"""Persist validated access policies separately from historical profile records."""
from __future__ import annotations

from sqlalchemy import ForeignKey, JSON, String
from sqlalchemy.orm import Mapped, mapped_column

from ._common import Base, TABLE_ARGS, foreign_key_target


class ProfilePolicy(Base):
    """One current policy per profile. This permits storing the active policy separately from
    historical profile records.
    
    .. author:: Rémi Verschuur <rverschuur@audit-io.fr>
    .. version:: 1.0.0
    """

    __tablename__ = "profile_policies"
    __table_args__ = TABLE_ARGS

    profile_id: Mapped[int] = mapped_column(
        ForeignKey(foreign_key_target("profiles")),
        primary_key=True,
        comment="Reference to the profile this policy belongs to"
    )
    default_duration: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        comment="The default duration for the profile policy",
    )
    maximum_duration: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        comment="The maximum duration for the profile policy",
    )
    networks: Mapped[list[str]] = mapped_column(
        JSON,
        nullable=False,
        comment="The networks associated with the profile policy",
    )
