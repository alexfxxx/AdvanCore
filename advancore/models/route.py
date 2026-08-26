from sqlalchemy import CheckConstraint, String
from sqlalchemy.orm import Mapped, mapped_column
from advancore.models.base import Base, TimestampMixin

class Route(TimestampMixin, Base):
    __tablename__ = "routes"
    __table_args__ = (CheckConstraint("status IN ('active', 'inactive')", name="ck_routes_status"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    route_code: Mapped[str] = mapped_column(String(40), nullable=False, unique=True)
    origin: Mapped[str] = mapped_column(String(160), nullable=False)
    destination: Mapped[str] = mapped_column(String(160), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="active")
