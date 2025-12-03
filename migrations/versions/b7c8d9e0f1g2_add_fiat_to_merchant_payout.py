"""Add fiat column to merchant_payout

Revision ID: b7c8d9e0f1g2
Revises: a1b2c3d4e5f6
Create Date: 2024-12-04
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "b7c8d9e0f1g2"
down_revision = "a1b2c3d4e5f6"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("merchant_payout", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("fiat", sa.String(), nullable=False, server_default="USD")
        )
        batch_op.alter_column("fiat", server_default=None)


def downgrade():
    with op.batch_alter_table("merchant_payout", schema=None) as batch_op:
        batch_op.drop_column("fiat")
