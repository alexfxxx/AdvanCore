from datetime import date
from decimal import Decimal

from sqlalchemy import CheckConstraint, Date, ForeignKey, Numeric
from sqlalchemy.orm import Mapped, mapped_column

from advancore.models.base import Base, TimestampMixin


class FuelEntry(TimestampMixin, Base):
    """One immutable, owner-entered vehicle fuelling fact."""

    __tablename__ = "fuel_entries"
    __table_args__ = (
        CheckConstraint("litres > 0", name="ck_fuel_entries_litres_positive"),
        CheckConstraint(
            "total_cost IS NULL OR total_cost >= 0",
            name="ck_fuel_entries_total_cost_nonnegative",
        ),
        CheckConstraint(
            "odometer_km IS NULL OR odometer_km >= 0",
            name="ck_fuel_entries_odometer_nonnegative",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    vehicle_id: Mapped[int] = mapped_column(
        ForeignKey("vehicles.id", ondelete="RESTRICT"), nullable=False
    )
    recorded_on: Mapped[date] = mapped_column(Date, nullable=False)
    litres: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    total_cost: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    odometer_km: Mapped[Decimal | None] = mapped_column(Numeric(12, 1), nullable=True)
