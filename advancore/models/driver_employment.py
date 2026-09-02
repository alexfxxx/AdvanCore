from datetime import date
from decimal import Decimal

from sqlalchemy import CheckConstraint, Date, ForeignKey, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from advancore.models.base import Base, TimestampMixin


class DriverEmploymentRecord(TimestampMixin, Base):
    __tablename__ = "driver_employment_records"
    __table_args__ = (
        CheckConstraint(
            "worker_category IN ('local_pr', 'foreign_levy')",
            name="ck_driver_employment_worker_category",
        ),
        CheckConstraint(
            "employment_status IN ('active', 'inactive')",
            name="ck_driver_employment_status",
        ),
        CheckConstraint("basic_salary >= 0", name="ck_driver_employment_basic_salary"),
        CheckConstraint(
            "employer_cpf_amount IS NULL OR employer_cpf_amount >= 0",
            name="ck_driver_employment_cpf_amount",
        ),
        CheckConstraint(
            "monthly_levy_amount IS NULL OR monthly_levy_amount >= 0",
            name="ck_driver_employment_levy_amount",
        ),
        CheckConstraint(
            "monthly_allowance IS NULL OR monthly_allowance >= 0",
            name="ck_driver_employment_allowance",
        ),
        CheckConstraint(
            "(worker_category = 'local_pr' AND monthly_levy_amount IS NULL) OR "
            "(worker_category = 'foreign_levy' AND employer_cpf_amount IS NULL)",
            name="ck_driver_employment_cost_category",
        ),
        UniqueConstraint(
            "driver_id", "effective_month", name="uq_driver_employment_driver_month"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    driver_id: Mapped[int] = mapped_column(
        ForeignKey("drivers.id", ondelete="RESTRICT"), nullable=False
    )
    effective_month: Mapped[date] = mapped_column(Date, nullable=False)
    worker_category: Mapped[str] = mapped_column(String(24), nullable=False)
    basic_salary: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    employer_cpf_amount: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    monthly_levy_amount: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    monthly_allowance: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    employment_status: Mapped[str] = mapped_column(String(16), nullable=False)

    driver: Mapped["Driver"] = relationship("Driver")
