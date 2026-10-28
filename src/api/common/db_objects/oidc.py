"""Database object for OpenID Connect (OIDC) configuration.

.. classes::
    - `OIDCConfig`: Represents the OIDC configuration for the application.

.. author:: Rémi Verschuur <rverschuur@audit-io.fr>
.. version:: 1.0.0
"""
from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ._common import (
    Base,
    TABLE_ARGS,
    user_id_column,
    numerical_pk_column,
)

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

    id: Mapped[int] = numerical_pk_column()
    user_id: Mapped[UUID] = user_id_column()
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
