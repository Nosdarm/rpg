"""create_status_effects_table

Revision ID: 0011
Revises: 0010
Create Date: 2025-07-02 13:57:15.167775

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '0011'
down_revision: Union[str, Sequence[str], None] = '0010'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('status_effects',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('guild_id', sa.BigInteger(), nullable=True),
        sa.Column('static_id', sa.Text(), nullable=False),
        sa.Column('name_i18n', postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column('description_i18n', postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column('effects_json', postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.ForeignKeyConstraint(['guild_id'], ['guild_configs.id'], name=op.f('fk_status_effects_guild_id_guild_configs'), ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_status_effects'))
    )
    op.create_index(op.f('ix_status_effects_guild_id'), 'status_effects', ['guild_id'], unique=False)
    op.create_index(op.f('ix_status_effects_id'), 'status_effects', ['id'], unique=False)
    op.create_index(op.f('ix_status_effects_static_id'), 'status_effects', ['static_id'], unique=False)

    # Unique constraint for (guild_id, static_id) where guild_id IS NOT NULL
    # This is effectively what the UniqueConstraint in the model would do if guild_id was not nullable.
    # For nullable guild_id, we need partial indexes for true uniqueness.
    op.create_index(
        'uq_status_effect_guild_static_id', # Name matches the one in model's __table_args__
        'status_effects',
        ['guild_id', 'static_id'],
        unique=True,
        postgresql_where=sa.column('guild_id').isnot(None)
    )

    # Unique constraint for static_id where guild_id IS NULL (global status effects)
    op.create_index(
        'ix_status_effect_global_static_id', # Name matches the one commented in model
        'status_effects',
        ['static_id'],
        unique=True,
        postgresql_where=sa.column('guild_id').is_(None)
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('ix_status_effect_global_static_id', table_name='status_effects', postgresql_where=sa.column('guild_id').is_(None))
    op.drop_index('uq_status_effect_guild_static_id', table_name='status_effects', postgresql_where=sa.column('guild_id').isnot(None))
    op.drop_index(op.f('ix_status_effects_static_id'), table_name='status_effects')
    op.drop_index(op.f('ix_status_effects_id'), table_name='status_effects')
    op.drop_index(op.f('ix_status_effects_guild_id'), table_name='status_effects')
    op.drop_table('status_effects')
