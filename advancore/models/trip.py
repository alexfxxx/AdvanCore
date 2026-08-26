from datetime import date
from sqlalchemy import CheckConstraint, Date, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column
from advancore.models.base import Base, TimestampMixin
class Trip(TimestampMixin, Base):
    __tablename__="trips"
    __table_args__=(CheckConstraint("status IN ('planned', 'completed', 'cancelled')",name="ck_trips_status"),)
    id: Mapped[int]=mapped_column(primary_key=True)
    trip_reference: Mapped[str]=mapped_column(String(40),unique=True,nullable=False)
    route_id: Mapped[int]=mapped_column(ForeignKey("routes.id",ondelete="RESTRICT"),nullable=False)
    service_date: Mapped[date]=mapped_column(Date,nullable=False)
    status: Mapped[str]=mapped_column(String(16),nullable=False,default="planned")
