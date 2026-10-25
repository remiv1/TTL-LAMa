"""Database object for OpenID Connect (OIDC) configuration.

.. classes::
    - `OIDCConfig`: Represents the OIDC configuration for the application.

.. author:: Rémi Verschuur <rverschuur@audit-io.fr>
.. version:: 1.0.0
"""
from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import String, ForeignKey, Integer, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ._common import Base, TABLE_ARGS, foreign_key_target

if TYPE_CHECKING:
    from .users import User

class OIDCUser(Base):
    """Represents an OIDC user parameters.

    :param user_id: Unique identifier of the user.
    :type user_id: UUID
    :param issuer: OIDC issuer URL.
    :type issuer: str
    :param subject: OIDC subject identifier.
    :type subject: str

    .. author:: Rémi Verschuur <rverschuur@audit-io.fr>
    .. version:: 1.0.0
    """

    __tablename__ = "oidc_users"
    __table_args__ = (
        UniqueConstraint(
            "issuer",
            "subject",
            name="uq_oidc_users_issuer_subject"
        ),
        TABLE_ARGS
    )

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True,
        comment="Unique identifier of the OIDC user",
    )
    user_id: Mapped[UUID] = mapped_column(
        String(36),
        ForeignKey(foreign_key_target("users")),
        comment="Unique identifier of the user",
    )
    issuer: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        comment="OIDC issuer URL",
    )
    subject: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        comment="OIDC subject identifier",
    )
    user: Mapped["User"] = relationship(
        "User",
        back_populates="oidc_users",
        uselist=False,
    )
