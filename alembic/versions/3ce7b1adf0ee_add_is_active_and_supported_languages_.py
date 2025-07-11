"""add_is_active_and_supported_languages_to_guild_config

Revision ID: 3ce7b1adf0ee
Revises: cdc86ea77142
Create Date: 2025-07-11 20:38:52.066035

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '3ce7b1adf0ee'
down_revision: Union[str, Sequence[str], None] = 'cdc86ea77142' # Assuming this is the correct previous revision
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('guild_configs', sa.Column('is_active', sa.Boolean(), server_default=sa.true(), nullable=False))
    op.add_column('guild_configs', sa.Column('supported_languages_json', postgresql.JSONB(astext_type=sa.Text()), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('guild_configs', 'supported_languages_json')
    op.drop_column('guild_configs', 'is_active')
