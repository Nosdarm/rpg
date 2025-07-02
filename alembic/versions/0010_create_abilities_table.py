"""create_abilities_table

Revision ID: 0010
Revises: 0009
Create Date: 2025-07-02 08:48:48.462934

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '0010'
down_revision: Union[str, Sequence[str], None] = '0009'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'abilities',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('guild_id', sa.BigInteger(), nullable=True),
        sa.Column('static_id', sa.Text(), nullable=False),
        sa.Column('name_i18n', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('description_i18n', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('properties_json', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.ForeignKeyConstraint(['guild_id'], ['guild_configs.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_abilities_guild_id'), 'abilities', ['guild_id'], unique=False)
    op.create_index(op.f('ix_abilities_id'), 'abilities', ['id'], unique=False) # SQLAlchemy добавляет это по умолчанию для PK, но для явности
    op.create_index(op.f('ix_abilities_static_id'), 'abilities', ['static_id'], unique=False)

    # Уникальное ограничение для (guild_id, static_id) где guild_id IS NOT NULL
    op.create_index(
        'uq_abilities_guild_static_id',
        'abilities',
        ['guild_id', 'static_id'],
        unique=True,
        postgresql_where=sa.column('guild_id').isnot(None)
    )
    # Уникальное ограничение для static_id где guild_id IS NULL (глобальные способности)
    op.create_index(
        'uq_abilities_global_static_id',
        'abilities',
        ['static_id'],
        unique=True,
        postgresql_where=sa.column('guild_id').is_(None)
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('uq_abilities_global_static_id', table_name='abilities', postgresql_where=sa.column('guild_id').is_(None))
    op.drop_index('uq_abilities_guild_static_id', table_name='abilities', postgresql_where=sa.column('guild_id').isnot(None))
    op.drop_index(op.f('ix_abilities_static_id'), table_name='abilities')
    op.drop_index(op.f('ix_abilities_id'), table_name='abilities')
    op.drop_index(op.f('ix_abilities_guild_id'), table_name='abilities')
    op.drop_table('abilities')
