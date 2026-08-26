from sqlalchemy import CheckConstraint, String
from sqlalchemy.orm import Mapped, mapped_column

from advancore.models.base import Base, TimestampMixin


class Vehicle(TimestampMixin, Base):
    """One owner-entered vehicle; no telematics or inferred values."""

    __tablename__ = "vehicles"
    __table_args__ = (
        CheckConstraint(
            "status IN ('active', 'out_of_service', 'retired')",
            name="ck_vehicles_status",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    registration_number: Mapped[str] = mapped_column(
        String(32), nullable=False, unique=True
    )
    make_model: Mapped[str | None] = mapped_column(String(120), nullable=True)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="active")
