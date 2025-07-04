"""add_attributes_json_to_player

Revision ID: e221edc41551
Revises: 565fa9a76d01
Create Date: 2025-07-04 17:50:30.247946

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e221edc41551'
down_revision: Union[str, Sequence[str], None] = '565fa9a76d01'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('players', sa.Column('attributes_json', sa.JSON(), nullable=False, server_default=sa.text("'{}'::jsonb")))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('players', 'attributes_json')
