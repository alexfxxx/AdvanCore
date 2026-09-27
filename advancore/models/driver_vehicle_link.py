from sqlalchemy import CheckConstraint, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from advancore.models.base import Base, TimestampMixin


class DriverVehicleLink(TimestampMixin, Base):
    __tablename__ = "driver_vehicle_links"
    __table_args__ = (
        UniqueConstraint("driver_id", "vehicle_id", name="uq_driver_vehicle_link"),
        CheckConstraint("status IN ('active', 'inactive')", name="ck_driver_vehicle_link_status"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    driver_id: Mapped[int] = mapped_column(ForeignKey("drivers.id", ondelete="RESTRICT"), nullable=False)
    vehicle_id: Mapped[int] = mapped_column(ForeignKey("vehicles.id", ondelete="RESTRICT"), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="active")
