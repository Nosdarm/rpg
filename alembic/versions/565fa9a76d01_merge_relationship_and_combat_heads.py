"""merge_relationship_and_combat_heads

Revision ID: 565fa9a76d01
Revises: 6344a0089ba3, 8a4788905319
Create Date: 2025-07-04 17:50:20.940242

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '565fa9a76d01'
down_revision: Union[str, Sequence[str], None] = ('6344a0089ba3', '8a4788905319')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
