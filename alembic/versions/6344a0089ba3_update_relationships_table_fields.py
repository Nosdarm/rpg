"""update_relationships_table_fields

Revision ID: 6344a0089ba3
Revises: fcb2e6d12a18
Create Date: 2025-07-05 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '6344a0089ba3'
down_revision: Union[str, Sequence[str], None] = 'fcb2e6d12a18'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('relationships', schema=None) as batch_op:
        # Добавляем source_log_id
        batch_op.add_column(sa.Column('source_log_id', sa.Integer(), nullable=True))
        batch_op.create_foreign_key(
            'fk_relationship_source_log_id', 'story_logs',
            ['source_log_id'], ['id'], ondelete='SET NULL'
        )
        batch_op.create_index('ix_relationships_source_log_id', ['source_log_id'], unique=False)

        # Удаляем ai_metadata_json
        batch_op.drop_column('ai_metadata_json')

        # Изменяем relationship_type_i18n на relationship_type (Text)
        # Данные из JSONB столбца relationship_type_i18n будут утеряны при этом подходе без дополнительной миграции данных.
        batch_op.drop_column('relationship_type_i18n')
        batch_op.add_column(sa.Column('relationship_type', sa.Text(), nullable=False, server_default='neutral'))
        batch_op.create_index('ix_relationships_relationship_type', ['relationship_type'], unique=False)


def downgrade() -> None:
    with op.batch_alter_table('relationships', schema=None) as batch_op:
        # Удаляем source_log_id
        # Порядок важен: сначала индекс и внешний ключ, потом столбец
        batch_op.drop_index('ix_relationships_source_log_id')
        batch_op.drop_constraint('fk_relationship_source_log_id', type_='foreignkey')
        batch_op.drop_column('source_log_id')

        # Возвращаем ai_metadata_json (тип был postgresql.JSONB)
        batch_op.add_column(sa.Column('ai_metadata_json', postgresql.JSONB(astext_type=sa.Text()), nullable=True))

        # Возвращаем relationship_type_i18n (тип был postgresql.JSONB)
        # Удаляем новый столбец relationship_type
        batch_op.drop_index('ix_relationships_relationship_type')
        batch_op.drop_column('relationship_type')
        # Добавляем старый столбец relationship_type_i18n
        batch_op.add_column(sa.Column('relationship_type_i18n', postgresql.JSONB(astext_type=sa.Text()), nullable=True))
        # В исходной миграции fcb2e6d12a18 не было индекса для relationship_type_i18n, поэтому не восстанавливаем его.
