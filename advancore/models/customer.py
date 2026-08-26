from sqlalchemy import CheckConstraint, String
from sqlalchemy.orm import Mapped, mapped_column
from advancore.models.base import Base, TimestampMixin

class Customer(TimestampMixin, Base):
    __tablename__ = "customers"
    __table_args__ = (CheckConstraint("status IN ('active', 'inactive')", name="ck_customers_status"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    customer_reference: Mapped[str | None] = mapped_column(String(40), nullable=True, unique=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="active")
