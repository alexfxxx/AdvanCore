from datetime import date
from decimal import Decimal

from sqlalchemy import CheckConstraint, Date, ForeignKey, Integer, Numeric, String
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
        CheckConstraint(
            "vehicle_type IS NULL OR vehicle_type IN ('Bus', 'lorry', 'car')",
            name="ck_vehicles_type",
        ),
        CheckConstraint(
            "passenger_capacity IS NULL OR passenger_capacity > 0",
            name="ck_vehicles_passenger_capacity_positive",
        ),
        CheckConstraint(
            "manufacture_year IS NULL OR manufacture_year BETWEEN 1886 AND 9999",
            name="ck_vehicles_manufacture_year",
        ),
        CheckConstraint("unladen_weight_kg IS NULL OR unladen_weight_kg >= 0", name="ck_vehicles_unladen_weight"),
        CheckConstraint("maximum_laden_weight_kg IS NULL OR maximum_laden_weight_kg >= 0", name="ck_vehicles_maximum_laden_weight"),
        CheckConstraint("parking_monthly_cost IS NULL OR parking_monthly_cost >= 0", name="ck_vehicles_parking_cost"),
        CheckConstraint("insurance_annual_amount IS NULL OR insurance_annual_amount >= 0", name="ck_vehicles_insurance_amount"),
        CheckConstraint("road_tax_amount IS NULL OR road_tax_amount >= 0", name="ck_vehicles_road_tax_amount"),
        CheckConstraint("original_loan_amount IS NULL OR original_loan_amount >= 0", name="ck_vehicles_original_loan_amount"),
        CheckConstraint("monthly_instalment IS NULL OR monthly_instalment >= 0", name="ck_vehicles_monthly_instalment"),
        CheckConstraint("loan_term_months IS NULL OR loan_term_months > 0", name="ck_vehicles_loan_term_months"),
        CheckConstraint(
            "(road_tax_amount IS NULL AND road_tax_period_months IS NULL) OR "
            "(road_tax_amount IS NOT NULL AND road_tax_period_months IN (6, 12))",
            name="ck_vehicles_road_tax_period",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    registration_number: Mapped[str] = mapped_column(
        String(32), nullable=False, unique=True
    )
    make_model: Mapped[str | None] = mapped_column(String(120), nullable=True)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="active")
    registered_owner_id: Mapped[int | None] = mapped_column(ForeignKey("legal_entities.id", ondelete="RESTRICT"), nullable=True)
    manufacture_year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    passenger_capacity: Mapped[int | None] = mapped_column(Integer, nullable=True)
    vehicle_type: Mapped[str | None] = mapped_column(String(16), nullable=True)
    propellant: Mapped[str | None] = mapped_column(String(40), nullable=True)
    scheme: Mapped[str | None] = mapped_column(String(80), nullable=True)
    chassis_number: Mapped[str | None] = mapped_column(String(80), nullable=True)
    engine_number: Mapped[str | None] = mapped_column(String(80), nullable=True)
    original_registration_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    lifespan_expiry: Mapped[date | None] = mapped_column(Date, nullable=True)
    coe_expiry: Mapped[date | None] = mapped_column(Date, nullable=True)
    primary_colour: Mapped[str | None] = mapped_column(String(40), nullable=True)
    unladen_weight_kg: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)
    maximum_laden_weight_kg: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)
    parking_provider: Mapped[str | None] = mapped_column(String(120), nullable=True)
    parking_location: Mapped[str | None] = mapped_column(String(200), nullable=True)
    parking_monthly_cost: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    insurance_provider: Mapped[str | None] = mapped_column(String(120), nullable=True)
    insurance_annual_amount: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    road_tax_amount: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    road_tax_period_months: Mapped[int | None] = mapped_column(Integer, nullable=True)
    finance_company: Mapped[str | None] = mapped_column(String(120), nullable=True)
    original_loan_amount: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    monthly_instalment: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    loan_start_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    loan_term_months: Mapped[int | None] = mapped_column(Integer, nullable=True)
