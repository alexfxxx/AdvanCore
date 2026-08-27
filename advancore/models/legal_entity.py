from sqlalchemy import CheckConstraint, String
from sqlalchemy.orm import Mapped, mapped_column

from advancore.models.base import Base, TimestampMixin


class LegalEntity(TimestampMixin, Base):
    """A configurable registered company/legal owner."""

    __tablename__ = "legal_entities"
    __table_args__ = (
        CheckConstraint("status IN ('active', 'inactive')", name="ck_legal_entities_status"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(160), nullable=False, unique=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="active")
