"""Separate diesel and AdBlue fuel facts."""
from alembic import op
import sqlalchemy as sa
revision='ffi217product'
down_revision='ffh216diesel'
branch_labels=None
depends_on=None
def upgrade():
    op.add_column('fuel_entries',sa.Column('product',sa.String(16),nullable=False,server_default='diesel'))
def downgrade():
    op.drop_column('fuel_entries','product')
