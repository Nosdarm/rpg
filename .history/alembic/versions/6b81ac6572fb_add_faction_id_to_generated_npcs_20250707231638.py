"""add_faction_id_to_generated_npcs

Revision ID: 6b81ac6572fb
Revises: 112c7a612f6c
Create Date: 2025-07-07 20:15:05.669242

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '6b81ac6572fb'
down_revision: Union[str, Sequence[str], None] = '112c7a612f6c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('generated_npcs', sa.Column('faction_id', sa.Integer(), nullable=True))
    op.create_foreign_key(
        'fk_generated_npc_faction_id',
        'generated_npcs', 'generated_factions',
        ['faction_id'], ['id']
    )
    op.create_index(op.f('ix_generated_npcs_faction_id'), 'generated_npcs', ['faction_id'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_generated_npcs_faction_id'), table_name='generated_npcs')
    op.drop_constraint('fk_generated_npc_faction_id', 'generated_npcs', type_='foreignkey')
    op.drop_column('generated_npcs', 'faction_id')
