"""financial entries

Revision ID: d1e111fin
Revises: c0e110fuel
"""
from alembic import op
import sqlalchemy as sa
revision="d1e111fin"; down_revision="c0e110fuel"; branch_labels=None; depends_on=None
def upgrade():
    op.create_table("financial_entries",
        sa.Column("id",sa.Integer(),primary_key=True),
        sa.Column("entry_date",sa.Date(),nullable=False),
        sa.Column("entry_type",sa.String(16),nullable=False),
        sa.Column("amount",sa.Numeric(14,2),nullable=False),
        sa.Column("currency_code",sa.String(3),nullable=False),
        sa.Column("description",sa.String(200),nullable=True),
        sa.Column("trip_id",sa.Integer(),sa.ForeignKey("trips.id",ondelete="RESTRICT"),nullable=True),
        sa.Column("customer_id",sa.Integer(),sa.ForeignKey("customers.id",ondelete="RESTRICT"),nullable=True),
        sa.Column("created_at",sa.DateTime(timezone=True),nullable=False),
        sa.Column("updated_at",sa.DateTime(timezone=True),nullable=False),
        sa.CheckConstraint("entry_type IN ('income', 'expense')",name="ck_financial_entries_type"),
        sa.CheckConstraint("amount > 0",name="ck_financial_entries_amount_positive"),
        sa.CheckConstraint("length(currency_code) = 3 AND currency_code = upper(currency_code) AND substr(currency_code, 1, 1) BETWEEN 'A' AND 'Z' AND substr(currency_code, 2, 1) BETWEEN 'A' AND 'Z' AND substr(currency_code, 3, 1) BETWEEN 'A' AND 'Z'",name="ck_financial_entries_currency_code"))
def downgrade(): op.drop_table("financial_entries")
