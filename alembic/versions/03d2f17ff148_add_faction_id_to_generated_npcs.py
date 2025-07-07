"""add faction_id to generated_npcs

Revision ID: 03d2f17ff148
Revises: 202407181210
Create Date: 2025-07-07 21:24:23.780576

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '03d2f17ff148'
down_revision: Union[str, Sequence[str], None] = '202407181210' # Ensure this matches your previous migration
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('generated_npcs',
                  sa.Column('faction_id', sa.Integer(), nullable=True)
                 )
    op.create_index('ix_generated_npcs_faction_id', 'generated_npcs', ['faction_id'], unique=False)
    op.create_foreign_key(
        'fk_generated_npc_faction_id',  # Constraint name from your model
        'generated_npcs',               # Source table
        'generated_factions',           # Referenced table (ensure this table exists)
        ['faction_id'],                 # Source columns
        ['id']                          # Referenced columns in 'generated_factions'
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint('fk_generated_npc_faction_id', 'generated_npcs', type_='foreignkey')
    op.drop_index('ix_generated_npcs_faction_id', table_name='generated_npcs')
    op.drop_column('generated_npcs', 'faction_id')
