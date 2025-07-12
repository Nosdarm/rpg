"""empty

Revision ID: 26f36bf8b493
Revises: c2c2f37c549a
Create Date: 2025-07-12 15:22:58.013415

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '26f36bf8b493'
down_revision: Union[str, Sequence[str], None] = 'c2c2f37c549a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
