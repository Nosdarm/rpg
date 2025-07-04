"""add_source_entity_to_active_status_effect

Revision ID: b3920fb77c09
Revises: 0005
Create Date: 2025-07-03 19:33:45.683206

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b3920fb77c09'
down_revision: Union[str, Sequence[str], None] = '0005'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('active_status_effects', sa.Column('source_entity_id', sa.Integer(), nullable=True))
    op.add_column('active_status_effects', sa.Column('source_entity_type', sa.Text(), nullable=True))
    op.create_index(op.f('ix_active_status_effects_source_entity_id'), 'active_status_effects', ['source_entity_id'], unique=False)
    op.create_index(op.f('ix_active_status_effects_source_entity_type'), 'active_status_effects', ['source_entity_type'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_active_status_effects_source_entity_type'), table_name='active_status_effects')
    op.drop_index(op.f('ix_active_status_effects_source_entity_id'), table_name='active_status_effects')
    op.drop_column('active_status_effects', 'source_entity_type')
    op.drop_column('active_status_effects', 'source_entity_id')
