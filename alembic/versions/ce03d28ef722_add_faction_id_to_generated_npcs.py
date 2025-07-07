"""add_faction_id_to_generated_npcs

Revision ID: ce03d28ef722
Revises: 8a72cf8116a2
Create Date: 2025-07-07 22:24:11.873459

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'ce03d28ef722'
down_revision: Union[str, Sequence[str], None] = '8a72cf8116a2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
