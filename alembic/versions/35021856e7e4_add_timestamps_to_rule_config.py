"""add_timestamps_to_rule_config

Revision ID: 35021856e7e4
Revises: 3ce7b1adf0ee
Create Date: 2025-07-11 20:39:49.808668

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '35021856e7e4'
down_revision: Union[str, Sequence[str], None] = '3ce7b1adf0ee'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('rule_configs', sa.Column('created_at', sa.TIMESTAMP(timezone=True), server_default=sa.func.now(), nullable=False))
    op.add_column('rule_configs', sa.Column('updated_at', sa.TIMESTAMP(timezone=True), server_default=sa.func.now(), nullable=False)) # The onupdate=func.now() is handled by SQLAlchemy ORM


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('rule_configs', 'updated_at')
    op.drop_column('rule_configs', 'created_at')
