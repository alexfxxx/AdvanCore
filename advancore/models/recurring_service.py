from datetime import date, time
from decimal import Decimal

from sqlalchemy import (
    CheckConstraint,
    Date,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Time,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from advancore.models.base import Base, TimestampMixin


class RecurringService(TimestampMixin, Base):
    __tablename__ = "recurring_services"
    __table_args__ = (
        CheckConstraint(
            "status IN ('active', 'paused', 'archived')",
            name="ck_recurring_services_status",
        ),
        CheckConstraint("monthly_amount >= 0", name="ck_recurring_services_monthly_amount"),
        CheckConstraint(
            "effective_end_date IS NULL OR effective_end_date >= effective_start_date",
            name="ck_recurring_services_effective_dates",
        ),
        UniqueConstraint(
            "customer_id",
            "service_reference",
            "effective_start_date",
            name="uq_recurring_services_customer_reference_start",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id", ondelete="RESTRICT"), nullable=False)
    route_id: Mapped[int] = mapped_column(ForeignKey("routes.id", ondelete="RESTRICT"), nullable=False)
    service_reference: Mapped[str] = mapped_column(String(40), nullable=False)
    vehicle_requirement: Mapped[str | None] = mapped_column(String(200), nullable=True)
    monthly_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    currency_code: Mapped[str] = mapped_column(String(3), nullable=False)
    effective_start_date: Mapped[date] = mapped_column(Date, nullable=False)
    effective_end_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="active")
    replaces_recurring_service_id: Mapped[int | None] = mapped_column(
        ForeignKey("recurring_services.id", ondelete="RESTRICT"), nullable=True
    )

    customer: Mapped["Customer"] = relationship("Customer")
    route: Mapped["Route"] = relationship("Route")
    replaced_service: Mapped["RecurringService | None"] = relationship(
        "RecurringService", remote_side="RecurringService.id"
    )
    days: Mapped[list["RecurringServiceDay"]] = relationship(
        "RecurringServiceDay", back_populates="service", cascade="all, delete-orphan", order_by="RecurringServiceDay.weekday"
    )
    stops: Mapped[list["RecurringServiceStop"]] = relationship(
        "RecurringServiceStop", back_populates="service", cascade="all, delete-orphan", order_by="RecurringServiceStop.stop_order"
    )


class RecurringServiceDay(Base):
    __tablename__ = "recurring_service_days"
    __table_args__ = (
        CheckConstraint("weekday >= 0 AND weekday <= 6", name="ck_recurring_service_days_weekday"),
        UniqueConstraint(
            "recurring_service_id",
            "weekday",
            name="uq_recurring_service_days_service_weekday",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    recurring_service_id: Mapped[int] = mapped_column(
        ForeignKey("recurring_services.id", ondelete="CASCADE"), nullable=False
    )
    weekday: Mapped[int] = mapped_column(Integer, nullable=False)

    service: Mapped["RecurringService"] = relationship("RecurringService", back_populates="days")


class RecurringServiceStop(Base):
    __tablename__ = "recurring_service_stops"
    __table_args__ = (
        CheckConstraint("stop_order >= 0", name="ck_recurring_service_stops_stop_order"),
        UniqueConstraint(
            "recurring_service_id",
            "stop_order",
            name="uq_recurring_service_stops_service_order",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    recurring_service_id: Mapped[int] = mapped_column(
        ForeignKey("recurring_services.id", ondelete="CASCADE"), nullable=False
    )
    stop_order: Mapped[int] = mapped_column(Integer, nullable=False)
    location_name: Mapped[str] = mapped_column(String(160), nullable=False)
    scheduled_time: Mapped[time] = mapped_column(Time, nullable=False)

    service: Mapped["RecurringService"] = relationship("RecurringService", back_populates="stops")
