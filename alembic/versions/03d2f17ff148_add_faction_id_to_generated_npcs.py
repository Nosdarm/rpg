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
down_revision: Union[str, Sequence[str], None] = '202407181210'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
