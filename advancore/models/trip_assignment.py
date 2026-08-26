from sqlalchemy import CheckConstraint, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from advancore.models.base import Base, TimestampMixin


class TripAssignment(TimestampMixin, Base):
    """One explicit driver and vehicle allocation for a trip."""

    __tablename__ = "trip_assignments"
    __table_args__ = (
        CheckConstraint(
            "status IN ('assigned', 'released')",
            name="ck_trip_assignments_status",
        ),
        UniqueConstraint("trip_id", name="uq_trip_assignments_trip_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    trip_id: Mapped[int] = mapped_column(
        ForeignKey("trips.id", ondelete="RESTRICT"), nullable=False
    )
    vehicle_id: Mapped[int] = mapped_column(
        ForeignKey("vehicles.id", ondelete="RESTRICT"), nullable=False
    )
    driver_id: Mapped[int] = mapped_column(
        ForeignKey("drivers.id", ondelete="RESTRICT"), nullable=False
    )
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="assigned"
    )
