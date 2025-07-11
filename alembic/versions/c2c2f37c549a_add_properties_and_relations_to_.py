"""add_properties_and_relations_to_location_and_guildconfig

Revision ID: c2c2f37c549a
Revises: 35021856e7e4
Create Date: 2025-07-11 20:41:11.416301

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql # For JSONB
from backend.models.custom_types import JsonBForSQLite # Assuming this is appropriate for SQLite if used by Alembic in some context

# revision identifiers, used by Alembic.
revision: str = 'c2c2f37c549a'
down_revision: Union[str, Sequence[str], None] = '35021856e7e4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Add the properties_json column to the locations table
    # Assuming the database is PostgreSQL for JSONB, otherwise use sa.JSON
    # The model uses JsonBForSQLite, which might imply a custom setup.
    # For broad compatibility, we'll use postgresql.JSONB if dialect is postgresql, else sa.JSON.
    # However, since the model specified JsonBForSQLite, we should respect that if it's intended for the migration.
    # For now, let's assume the target is PostgreSQL and use JSONB.
    # If JsonBForSQLite is a custom type that works with alembic, it should be used.
    # Given the project uses asyncpg, PostgreSQL is the likely target.

    op.add_column('locations', sa.Column('properties_json', postgresql.JSONB(astext_type=sa.Text()), nullable=True))
    # Note: The relationships added in the models (guild, parent_location, child_locations in Location;
    # locations in GuildConfig) are ORM constructs and typically do not require separate schema changes
    # if the foreign key columns (guild_id, parent_location_id) already exist and are correctly defined.
    # These relationships primarily affect how SQLAlchemy loads and interacts with related objects.


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('locations', 'properties_json')
