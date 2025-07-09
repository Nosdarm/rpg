"""add_party_npc_memories_table

Revision ID: 711257a22d1d
Revises: 6b81ac6572fb
Create Date: 2025-07-09 17:47:45.820251

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '711257a22d1d'
down_revision: Union[str, Sequence[str], None] = '6b81ac6572fb'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'party_npc_memories',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('guild_id', sa.BigInteger(), nullable=False),
        sa.Column('party_id', sa.Integer(), nullable=False),
        sa.Column('npc_id', sa.Integer(), nullable=False),
        sa.Column('event_type', sa.Text(), nullable=True),
        sa.Column('memory_details_i18n', sa.JSON(), nullable=True, server_default=sa.text("'{}'::jsonb")),
        sa.Column('memory_data_json', sa.JSON(), nullable=True, server_default=sa.text("'{}'::jsonb")),
        sa.Column('timestamp', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('ai_significance_score', sa.Integer(), nullable=True),

        sa.ForeignKeyConstraint(['guild_id'], ['guild_configs.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['party_id'], ['parties.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['npc_id'], ['generated_npcs.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_party_npc_memories_guild_id'), 'party_npc_memories', ['guild_id'], unique=False)
    op.create_index(op.f('ix_party_npc_memories_party_id'), 'party_npc_memories', ['party_id'], unique=False)
    op.create_index(op.f('ix_party_npc_memories_npc_id'), 'party_npc_memories', ['npc_id'], unique=False)
    op.create_index(op.f('ix_party_npc_memories_event_type'), 'party_npc_memories', ['event_type'], unique=False)
    op.create_index(op.f('ix_party_npc_memories_timestamp'), 'party_npc_memories', ['timestamp'], unique=False)
    op.create_index(op.f('ix_party_npc_memories_id'), 'party_npc_memories', ['id'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_party_npc_memories_id'), table_name='party_npc_memories')
    op.drop_index(op.f('ix_party_npc_memories_timestamp'), table_name='party_npc_memories')
    op.drop_index(op.f('ix_party_npc_memories_event_type'), table_name='party_npc_memories')
    op.drop_index(op.f('ix_party_npc_memories_npc_id'), table_name='party_npc_memories')
    op.drop_index(op.f('ix_party_npc_memories_party_id'), table_name='party_npc_memories')
    op.drop_index(op.f('ix_party_npc_memories_guild_id'), table_name='party_npc_memories')
    op.drop_table('party_npc_memories')
