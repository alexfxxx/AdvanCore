from sqlalchemy import CheckConstraint, String
from sqlalchemy.orm import Mapped, mapped_column

from advancore.models.base import Base, TimestampMixin


class Driver(TimestampMixin, Base):
    __tablename__ = "drivers"
    __table_args__ = (
        CheckConstraint(
            "status IN ('active', 'unavailable', 'retired')",
            name="ck_drivers_status",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    employee_reference: Mapped[str | None] = mapped_column(
        String(40), nullable=True, unique=True
    )
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="active")
