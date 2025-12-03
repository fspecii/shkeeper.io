"""Add fiat currency to merchant_balance

This migration adds a fiat currency dimension to MerchantBalance,
allowing tracking of balances per-crypto AND per-fiat currency pair.
Existing records default to 'USD'.

Revision ID: a1b2c3d4e5f6
Revises: cd6076e578ca
Create Date: 2024-12-03

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'a1b2c3d4e5f6'
down_revision = 'cd6076e578ca'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('merchant_balance', schema=None) as batch_op:
        # Add fiat column with default value for existing records
        batch_op.add_column(sa.Column('fiat', sa.String(), nullable=False, server_default='USD'))

        # Drop old unique constraint (merchant_id, crypto)
        batch_op.drop_constraint('uq_merchant_balance_merchant_id', type_='unique')

        # Create new unique constraint including fiat
        batch_op.create_unique_constraint(
            'uq_merchant_balance_merchant_id',
            ['merchant_id', 'crypto', 'fiat']
        )


def downgrade():
    with op.batch_alter_table('merchant_balance', schema=None) as batch_op:
        # Drop new constraint
        batch_op.drop_constraint('uq_merchant_balance_merchant_id', type_='unique')

        # Recreate old constraint (merchant_id, crypto)
        batch_op.create_unique_constraint(
            'uq_merchant_balance_merchant_id',
            ['merchant_id', 'crypto']
        )

        # Remove fiat column
        batch_op.drop_column('fiat')
