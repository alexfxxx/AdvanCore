"""Local-only operating records for recurring route costs and vehicle profitability."""

from datetime import date
from decimal import Decimal

from sqlalchemy import CheckConstraint, Date, ForeignKey, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from advancore.models.base import Base, TimestampMixin


class Subcontractor(TimestampMixin, Base):
    __tablename__ = "subcontractors"
    __table_args__ = (CheckConstraint("status IN ('active', 'archived')", name="ck_subcontractors_status"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    company_name: Mapped[str] = mapped_column(String(160), nullable=False, unique=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="active")


class SubcontractorDriver(TimestampMixin, Base):
    __tablename__ = "subcontractor_drivers"
    id: Mapped[int] = mapped_column(primary_key=True)
    subcontractor_id: Mapped[int] = mapped_column(ForeignKey("subcontractors.id", ondelete="RESTRICT"), nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    contact_number: Mapped[str | None] = mapped_column(String(40), nullable=True)


class SubcontractorVehicle(TimestampMixin, Base):
    __tablename__ = "subcontractor_vehicles"
    __table_args__ = (UniqueConstraint("subcontractor_id", "vehicle_number", name="uq_subcontractor_vehicle_number"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    subcontractor_id: Mapped[int] = mapped_column(ForeignKey("subcontractors.id", ondelete="RESTRICT"), nullable=False)
    vehicle_number: Mapped[str] = mapped_column(String(32), nullable=False)
    capacity: Mapped[int | None] = mapped_column(nullable=True)


class RecurringRouteAssignment(TimestampMixin, Base):
    __tablename__ = "recurring_route_assignments"
    __table_args__ = (
        CheckConstraint("assignment_type IN ('own_fleet', 'subcontractor')", name="ck_route_assignment_type"),
        CheckConstraint("status IN ('active', 'ended')", name="ck_route_assignment_status"),
        CheckConstraint("monthly_subcontractor_cost IS NULL OR monthly_subcontractor_cost >= 0", name="ck_route_assignment_monthly_cost"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    recurring_service_id: Mapped[int] = mapped_column(ForeignKey("recurring_services.id", ondelete="RESTRICT"), nullable=False)
    assignment_type: Mapped[str] = mapped_column(String(20), nullable=False)
    vehicle_id: Mapped[int | None] = mapped_column(ForeignKey("vehicles.id", ondelete="RESTRICT"), nullable=True)
    driver_id: Mapped[int | None] = mapped_column(ForeignKey("drivers.id", ondelete="RESTRICT"), nullable=True)
    subcontractor_vehicle_id: Mapped[int | None] = mapped_column(ForeignKey("subcontractor_vehicles.id", ondelete="RESTRICT"), nullable=True)
    subcontractor_driver_id: Mapped[int | None] = mapped_column(ForeignKey("subcontractor_drivers.id", ondelete="RESTRICT"), nullable=True)
    monthly_subcontractor_cost: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    effective_start_date: Mapped[date] = mapped_column(Date, nullable=False)
    effective_end_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="active")
    remarks: Mapped[str | None] = mapped_column(String(300), nullable=True)


class MaintenanceEntry(TimestampMixin, Base):
    __tablename__ = "maintenance_entries"
    __table_args__ = (CheckConstraint("amount > 0", name="ck_maintenance_amount_positive"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    vehicle_id: Mapped[int] = mapped_column(ForeignKey("vehicles.id", ondelete="RESTRICT"), nullable=False)
    service_date: Mapped[date] = mapped_column(Date, nullable=False)
    vendor: Mapped[str] = mapped_column(String(160), nullable=False)
    service_type: Mapped[str] = mapped_column(String(120), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    remarks: Mapped[str | None] = mapped_column(String(300), nullable=True)
