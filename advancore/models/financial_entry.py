from datetime import date
from decimal import Decimal

from sqlalchemy import CheckConstraint, Date, ForeignKey, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from advancore.models.base import Base, TimestampMixin


class FinancialEntry(TimestampMixin, Base):
    """One immutable, explicitly denominated business entry."""

    __tablename__ = "financial_entries"
    __table_args__ = (
        CheckConstraint(
            "entry_type IN ('income', 'expense')",
            name="ck_financial_entries_type",
        ),
        CheckConstraint("amount > 0", name="ck_financial_entries_amount_positive"),
        CheckConstraint(
            "length(currency_code) = 3 "
            "AND currency_code = upper(currency_code) "
            "AND substr(currency_code, 1, 1) BETWEEN 'A' AND 'Z' "
            "AND substr(currency_code, 2, 1) BETWEEN 'A' AND 'Z' "
            "AND substr(currency_code, 3, 1) BETWEEN 'A' AND 'Z'",
            name="ck_financial_entries_currency_code",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    entry_date: Mapped[date] = mapped_column(Date, nullable=False)
    entry_type: Mapped[str] = mapped_column(String(16), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    currency_code: Mapped[str] = mapped_column(String(3), nullable=False)
    description: Mapped[str | None] = mapped_column(String(200), nullable=True)
    trip_id: Mapped[int | None] = mapped_column(
        ForeignKey("trips.id", ondelete="RESTRICT"), nullable=True
    )
    customer_id: Mapped[int | None] = mapped_column(
        ForeignKey("customers.id", ondelete="RESTRICT"), nullable=True
    )
