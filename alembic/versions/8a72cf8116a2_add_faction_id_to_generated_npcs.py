"""add_faction_id_to_generated_npcs

Revision ID: 8a72cf8116a2
Revises: 03d2f17ff148
Create Date: 2025-07-07 22:07:17.915057

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '8a72cf8116a2'
down_revision: Union[str, Sequence[str], None] = '03d2f17ff148'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
