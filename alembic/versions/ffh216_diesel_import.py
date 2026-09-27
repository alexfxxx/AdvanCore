"""Diesel import provenance and approved local pricing configuration."""
from alembic import op
import sqlalchemy as sa
revision='ffh216diesel'
down_revision='ffg215balances'
branch_labels=None
depends_on=None
def upgrade():
    op.create_table('diesel_rates',sa.Column('effective_on',sa.Date(),primary_key=True),sa.Column('price',sa.Numeric(8,3),nullable=False))
    op.create_table('diesel_transactions',sa.Column('transaction_id',sa.String(80),primary_key=True),sa.Column('record',sa.JSON(),nullable=False))
    op.create_table('diesel_settings',sa.Column('key',sa.String(80),primary_key=True),sa.Column('value',sa.JSON(),nullable=False))
def downgrade():
    op.drop_table('diesel_settings');op.drop_table('diesel_transactions');op.drop_table('diesel_rates')
