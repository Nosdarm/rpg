"""use_jsonb_for_location_fields

Revision ID: 0005
Revises: 0004
Create Date: 2025-07-03 03:49:24.398575

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '0005'
down_revision: Union[str, Sequence[str], None] = '0004'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.alter_column('locations', 'name_i18n',
               existing_type=sa.JSON(),
               type_=postgresql.JSONB(astext_type=sa.Text()),
               existing_nullable=False,
               postgresql_using='name_i18n::jsonb')
    op.alter_column('locations', 'descriptions_i18n',
               existing_type=sa.JSON(),
               type_=postgresql.JSONB(astext_type=sa.Text()),
               existing_nullable=False,
               postgresql_using='descriptions_i18n::jsonb')
    op.alter_column('locations', 'coordinates_json',
               existing_type=sa.JSON(),
               type_=postgresql.JSONB(astext_type=sa.Text()),
               existing_nullable=True,
               postgresql_using='coordinates_json::jsonb')
    op.alter_column('locations', 'neighbor_locations_json',
               existing_type=sa.JSON(),
               type_=postgresql.JSONB(astext_type=sa.Text()),
               existing_nullable=True,
               postgresql_using='neighbor_locations_json::jsonb')
    op.alter_column('locations', 'generated_details_json',
               existing_type=sa.JSON(),
               type_=postgresql.JSONB(astext_type=sa.Text()),
               existing_nullable=True,
               postgresql_using='generated_details_json::jsonb')
    op.alter_column('locations', 'ai_metadata_json',
               existing_type=sa.JSON(),
               type_=postgresql.JSONB(astext_type=sa.Text()),
               existing_nullable=True,
               postgresql_using='ai_metadata_json::jsonb')


def downgrade() -> None:
    """Downgrade schema."""
    op.alter_column('locations', 'ai_metadata_json',
               existing_type=postgresql.JSONB(astext_type=sa.Text()),
               type_=sa.JSON(),
               existing_nullable=True,
               postgresql_using='ai_metadata_json::json')
    op.alter_column('locations', 'generated_details_json',
               existing_type=postgresql.JSONB(astext_type=sa.Text()),
               type_=sa.JSON(),
               existing_nullable=True,
               postgresql_using='generated_details_json::json')
    op.alter_column('locations', 'neighbor_locations_json',
               existing_type=postgresql.JSONB(astext_type=sa.Text()),
               type_=sa.JSON(),
               existing_nullable=True,
               postgresql_using='neighbor_locations_json::json')
    op.alter_column('locations', 'coordinates_json',
               existing_type=postgresql.JSONB(astext_type=sa.Text()),
               type_=sa.JSON(),
               existing_nullable=True,
               postgresql_using='coordinates_json::json')
    op.alter_column('locations', 'descriptions_i18n',
               existing_type=postgresql.JSONB(astext_type=sa.Text()),
               type_=sa.JSON(),
               existing_nullable=False,
               postgresql_using='descriptions_i18n::json')
    op.alter_column('locations', 'name_i18n',
               existing_type=postgresql.JSONB(astext_type=sa.Text()),
               type_=sa.JSON(),
               existing_nullable=False,
               postgresql_using='name_i18n::json')
