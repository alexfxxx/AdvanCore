from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from advancore.models.base import Base, TimestampMixin


class FuelMarketSnapshot(TimestampMixin, Base):
    """One verified Shell/SPC gross-diesel observation for a Singapore day."""

    __tablename__ = "fuel_market_snapshots"
    __table_args__ = (
        UniqueConstraint("observed_on", name="uq_fuel_market_snapshots_observed_on"),
        CheckConstraint("shell_price_per_litre > 0", name="ck_fuel_market_shell_price"),
        CheckConstraint("spc_price_per_litre > 0", name="ck_fuel_market_spc_price"),
        CheckConstraint("benchmark_price_per_litre > 0", name="ck_fuel_market_benchmark_price"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    observed_on: Mapped[date] = mapped_column(Date, nullable=False)
    shell_price_per_litre: Mapped[Decimal] = mapped_column(Numeric(10, 4), nullable=False)
    spc_price_per_litre: Mapped[Decimal] = mapped_column(Numeric(10, 4), nullable=False)
    benchmark_price_per_litre: Mapped[Decimal] = mapped_column(Numeric(10, 4), nullable=False)
    shell_source_updated_at: Mapped[str] = mapped_column(String(80), nullable=False)
    spc_source_updated_at: Mapped[str] = mapped_column(String(80), nullable=False)
    refreshed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class FuelMarketRefreshState(TimestampMixin, Base):
    """Singleton operational evidence for the last bounded refresh attempt."""

    __tablename__ = "fuel_market_refresh_state"
    __table_args__ = (
        CheckConstraint("id = 1", name="ck_fuel_market_refresh_singleton"),
        CheckConstraint("consecutive_failures >= 0", name="ck_fuel_market_refresh_failures"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    last_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    consecutive_failures: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_failure_code: Mapped[str | None] = mapped_column(String(40), nullable=True)
    last_failure_summary: Mapped[str | None] = mapped_column(String(240), nullable=True)


class RecurringServiceFuelRule(TimestampMixin, Base):
    """Forward-only contract facts used for a draft fuel adjustment."""

    __tablename__ = "recurring_service_fuel_rules"
    __table_args__ = (
        UniqueConstraint(
            "recurring_service_id",
            "effective_from",
            name="uq_recurring_service_fuel_rule_effective",
        ),
        CheckConstraint("baseline_price_per_litre > 0", name="ck_fuel_rule_baseline"),
        CheckConstraint(
            "fuel_cost_share_percent >= 0 AND fuel_cost_share_percent <= 100",
            name="ck_fuel_rule_cost_share",
        ),
        CheckConstraint(
            "tolerance_percent >= 0 AND tolerance_percent <= 100",
            name="ck_fuel_rule_tolerance",
        ),
        CheckConstraint(
            "effective_to IS NULL OR effective_to >= effective_from",
            name="ck_fuel_rule_effective_dates",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    recurring_service_id: Mapped[int] = mapped_column(
        ForeignKey("recurring_services.id", ondelete="RESTRICT"), nullable=False
    )
    effective_from: Mapped[date] = mapped_column(Date, nullable=False)
    effective_to: Mapped[date | None] = mapped_column(Date, nullable=True)
    baseline_price_per_litre: Mapped[Decimal] = mapped_column(Numeric(10, 4), nullable=False)
    fuel_cost_share_percent: Mapped[Decimal] = mapped_column(Numeric(7, 4), nullable=False)
    tolerance_percent: Mapped[Decimal] = mapped_column(Numeric(7, 4), nullable=False)

    recurring_service: Mapped["RecurringService"] = relationship("RecurringService")
